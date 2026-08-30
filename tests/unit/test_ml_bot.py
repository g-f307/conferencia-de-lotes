from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.classificador_divergencia import (
    ClassificadorDivergencia,
    PredicaoCausa,
)
from src.ml_audit import MLDecisionRecorder
from src.ml_bot import (
    MLBotContext,
    MLBotInputError,
    MLBotService,
    write_ml_bot_result,
)

pytestmark = pytest.mark.unit


def context() -> MLBotContext:
    return MLBotContext(
        execution_id="exec-113",
        correlation_id="corr-113",
        root_task_id="root-113",
        task_id="task-ml-113",
        parent_task_id="task-consolidacao-113",
        predecessor_task_ids=("task-consolidacao-113",),
    )


def record(
    status: str = "DIVERGENCIA",
    *,
    observation: str = "quantidade divergente no recebimento",
) -> dict[str, object]:
    return {
        "lote_id": "L001",
        "status_operacional": status,
        "validacao": {
            "campos_originais": {"observacao": observation},
        },
    }


def envelope(*records: dict[str, object]) -> dict[str, object]:
    return {"payload": {"records": list(records)}}


def recorder() -> MLDecisionRecorder:
    return MLDecisionRecorder(
        "classificador-ml-v1",
        "exec-113",
        clock=lambda: datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    )


class ControlledProvider:
    def __init__(
        self,
        response: PredicaoCausa | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, float]] = []

    def classificar(self, observacao: str, timeout_seconds: float) -> PredicaoCausa:
        self.calls.append((observacao, timeout_seconds))
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def classifier(provider: ControlledProvider, *, enabled: bool = True):
    moments = iter([1.0, 1.025])
    return ClassificadorDivergencia(
        enabled=enabled,
        confianca_minima=0.8,
        timeout_seconds=0.4,
        provedor=provider if enabled else None,
        clock=lambda: next(moments),
    )


def test_enriquece_divergencia_sem_alterar_status_deterministico() -> None:
    provider = ControlledProvider(PredicaoCausa("estoque_insuficiente", 0.94))
    service = MLBotService(classifier(provider), recorder())

    result = service.process(envelope(record()), context())

    assert result["status"] == "SUCCESS"
    assert result["execution_id"] == "exec-113"
    assert result["correlation_id"] == "corr-113"
    assert result["task_id"] == "task-ml-113"
    assert result["predecessor_task_ids"] == ["task-consolidacao-113"]
    assert provider.calls == [("quantidade divergente no recebimento", 0.4)]
    item = result["payload"]["records"][0]
    decision = item["decisao_ml"]
    assert item["resultado_deterministico"] == "DIVERGENCIA"
    assert decision["resultado_aplicado"] == "DIVERGENCIA"
    assert decision["causa_provavel"] == "estoque_insuficiente"
    assert decision["confianca_ml"] == 0.94
    assert decision["origem_decisao"] == "ml"
    assert decision["motivo_fallback"] is None
    assert decision["latencia_ms"] == 25.0


def test_ml_desabilitado_nao_chama_provedor_e_produz_saida_valida() -> None:
    provider = ControlledProvider(PredicaoCausa("nao_deve_ocorrer", 0.99))
    service = MLBotService(classifier(provider, enabled=False), recorder())

    result = service.process(envelope(record()), context())

    assert provider.calls == []
    assert result["status"] == "SUCCESS"
    assert result["modo_degradado"] is False
    decision = result["payload"]["ml_decisions"][0]
    assert decision["origem_decisao"] == "fallback"
    assert decision["motivo_fallback"] == "ml_desabilitado"
    assert decision["resultado_aplicado"] == "DIVERGENCIA"


@pytest.mark.parametrize(
    ("provider", "expected_reason"),
    [
        (ControlledProvider(error=ConnectionError("offline")), "indisponibilidade"),
        (ControlledProvider(error=TimeoutError("demorado")), "timeout"),
        (ControlledProvider(response=PredicaoCausa("incerta", 0.5)), "baixa_confianca"),
    ],
    ids=["indisponibilidade", "timeout", "baixa-confianca"],
)
def test_falhas_do_ml_geram_conclusao_parcial_auditavel(
    provider: ControlledProvider,
    expected_reason: str,
) -> None:
    result = MLBotService(classifier(provider), recorder()).process(
        envelope(record()),
        context(),
    )

    assert result["status"] == "PARTIALLY_COMPLETED"
    assert result["modo_degradado"] is True
    assert result["motivo_fallback"] == expected_reason
    decision = result["payload"]["ml_decisions"][0]
    assert decision["motivo_fallback"] == expected_reason
    assert decision["resultado_aplicado"] == "DIVERGENCIA"


def test_resposta_malformada_do_classificador_nao_interrompe_pipeline() -> None:
    class MalformedClassifier:
        def classificar(self, observacao: str):
            return {"causa": "contrato_invalido"}

    result = MLBotService(MalformedClassifier(), recorder()).process(  # type: ignore[arg-type]
        envelope(record()),
        context(),
    )

    decision = result["payload"]["ml_decisions"][0]
    assert result["status"] == "PARTIALLY_COMPLETED"
    assert decision["motivo_fallback"] == "resposta_invalida"
    assert decision["resultado_aplicado"] == "DIVERGENCIA"


def test_sem_itens_elegiveis_termina_sem_chamar_classificador() -> None:
    class ExplodingClassifier:
        def classificar(self, observacao: str):
            raise AssertionError("não deveria ser chamado")

    result = MLBotService(ExplodingClassifier(), recorder()).process(  # type: ignore[arg-type]
        envelope(record("APROVADO"), record("ERRO_ITEM")),
        context(),
    )

    assert result["status"] == "SUCCESS"
    assert result["payload"]["eligible_items"] == 0
    assert result["payload"]["skipped_items"] == 2
    assert result["payload"]["ml_decisions"] == []
    assert all(
        item["resultado_deterministico"] in {"APROVADO", "ERRO_ITEM"}
        for item in result["payload"]["records"]
    )


@pytest.mark.parametrize(
    "invalid",
    [{}, {"payload": None}, {"payload": {"records": {}}}],
)
def test_rejeita_contrato_de_consolidacao_invalido(invalid) -> None:
    provider = ControlledProvider(PredicaoCausa("causa", 0.9))

    with pytest.raises(MLBotInputError):
        MLBotService(classifier(provider), recorder()).process(invalid, context())


def test_persiste_resultado_atomicamente(tmp_path: Path) -> None:
    destination = tmp_path / "resultado" / "ml.json"

    write_ml_bot_result({"status": "SUCCESS"}, destination)

    assert destination.read_text(encoding="utf-8").strip().startswith("{")
    assert not destination.with_suffix(".json.tmp").exists()
