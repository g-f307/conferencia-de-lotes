from __future__ import annotations

import json

import pytest

from src.classificador_divergencia import ClassificadorDivergencia, PredicaoCausa
from src.config import Settings
from src.item_processor import ItemProcessor
from src.logging_config import configure_logging
from src.ml_audit import MLDecisionRecorder
from src.ml_client import MLClient

pytestmark = pytest.mark.integration


def ambiguous_item(index: int = 1, *, observacao: str = "Conferir"):
    return {
        "lote_id": f"L{index:03d}",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "A",
        "status": "EM ANALISE",
        "responsavel": "Operador",
        "data": "2026-08-19",
        "observacao": observacao,
    }


def records(log_file):
    return [
        json.loads(line)
        for line in log_file.read_text(encoding="utf-8").splitlines()
    ]


class SuccessfulProvider:
    def classificar(self, observacao: str, timeout_seconds: float):
        return PredicaoCausa("falha_de_calibracao", 0.91)


def test_enriquecimento_ml_preserva_status_e_possui_contexto_no_json_lines(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("BOT_ID", "bot-ml-test")
    monkeypatch.setenv("EXECUTION_ID", "exec-ml-123")
    settings = Settings.from_env(tmp_path)
    log_file = tmp_path / "logs" / "execucao.log"
    configure_logging(log_file, settings)
    times = iter([10.0, 10.025])
    classifier = ClassificadorDivergencia(
        enabled=True,
        confianca_minima=0.85,
        timeout_seconds=1,
        provedor=SuccessfulProvider(),
        clock=lambda: next(times),
    )
    processor = ItemProcessor(
        {"L001"},
        divergence_classifier=classifier,
        decision_recorder=MLDecisionRecorder(
            settings.bot_id,
            settings.execution_id,
        ),
    )

    classification = processor.process(ambiguous_item())

    assert classification.resultado == "REVISAO"
    assert classification.ml_decision is not None
    assert classification.enriquecimento_ml is not None
    assert classification.enriquecimento_ml.causa_provavel == "falha_de_calibracao"
    audit = next(record for record in records(log_file) if record["evento"] == "ENRIQUECIMENTO_ML")
    assert audit["bot_id"] == "bot-ml-test"
    assert audit["execution_id"] == "exec-ml-123"
    assert audit["detalhes"]["lote_id"] == "L001"
    assert audit["detalhes"]["classe"] == "falha_de_calibracao"
    assert audit["detalhes"]["probabilidade"] == 0.91
    assert audit["detalhes"]["latencia_ms"] == 25.0
    assert audit["detalhes"]["resultado_aplicado"] == "REVISAO"
    assert audit["detalhes"]["causa_provavel"] == "falha_de_calibracao"
    assert audit["detalhes"]["origem_decisao"] == "ml"
    assert audit["detalhes"]["confianca_ml"] == 0.91
    assert audit["detalhes"]["motivo_fallback"] is None


class OfflineProvider:
    def classificar(self, observacao: str, timeout_seconds: float):
        raise TimeoutError("detalhe interno que nao deve ser registrado")


def test_fallback_nao_altera_status_nem_expoe_observacao_ou_traceback(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("BOT_ID", "bot-ml-test")
    monkeypatch.setenv("EXECUTION_ID", "exec-ml-offline")
    settings = Settings.from_env(tmp_path)
    log_file = tmp_path / "logs" / "execucao.log"
    configure_logging(log_file, settings)
    secret_observation = "observacao confidencial do lote"
    times = iter([20.0, 20.1])
    classifier = ClassificadorDivergencia(
        enabled=True,
        confianca_minima=0.85,
        timeout_seconds=1,
        provedor=OfflineProvider(),
        clock=lambda: next(times),
    )
    processor = ItemProcessor(
        {"L001"},
        divergence_classifier=classifier,
        decision_recorder=MLDecisionRecorder(
            settings.bot_id,
            settings.execution_id,
        ),
    )

    result = processor.process(ambiguous_item(observacao=secret_observation))

    assert result.resultado == "REVISAO"
    assert result.enriquecimento_ml is not None
    assert result.enriquecimento_ml.motivo_fallback == "timeout"
    content = log_file.read_text(encoding="utf-8")
    audit = next(
        record
        for record in records(log_file)
        if record["evento"] == "FALLBACK_CLASSIFICADOR_DIVERGENCIA"
        and record["detalhes"].get("lote_id") == "L001"
    )
    assert audit["detalhes"]["resultado_aplicado"] == "REVISAO"
    assert audit["detalhes"]["causa_provavel"] == "nao_classificado"
    assert audit["detalhes"]["origem_decisao"] == "fallback"
    assert audit["detalhes"]["confianca_ml"] is None
    assert audit["detalhes"]["motivo_fallback"] == "timeout"
    assert "exception" not in audit["detalhes"]
    assert secret_observation not in content


def test_falha_de_comunicacao_do_cliente_legado_registra_tipo_sem_traceback(tmp_path):
    settings = Settings.from_env(tmp_path)
    log_file = tmp_path / "logs" / "execucao.log"
    configure_logging(log_file, settings)

    def unavailable(url: str, body: bytes, timeout: float) -> bytes:
        raise TimeoutError("detalhe interno que nao deve ser registrado")

    client = MLClient("http://ml.test", 1, transport=unavailable)
    result = client.classificar(
        lote_id="L001",
        status_raw="PENDENTE",
        turno="B",
        tem_obs=False,
    )

    assert result is None
    record = json.loads(log_file.read_text(encoding="utf-8"))
    assert record["evento"] == "FALHA_COMUNICACAO_ML"
    assert record["detalhes"]["ml_error_type"] == "TimeoutError"
    assert record["detalhes"]["falhas_consecutivas"] == 1
    assert "exception" not in record["detalhes"]
    assert "detalhe interno" not in record["detalhes"]["mensagem"]


def test_abertura_do_circuit_breaker_legado_e_registrada_uma_unica_vez(tmp_path):
    settings = Settings.from_env(tmp_path)
    log_file = tmp_path / "logs" / "execucao.log"
    configure_logging(log_file, settings)
    network_calls = 0

    def unavailable(url: str, body: bytes, timeout: float) -> bytes:
        nonlocal network_calls
        network_calls += 1
        raise ConnectionError("offline")

    client = MLClient("http://ml.test", 1, transport=unavailable)
    for index in range(7):
        assert client.classificar(
            lote_id=f"L{index:03d}",
            status_raw="PENDENTE",
            turno="C",
            tem_obs=False,
        ) is None

    events = [record["evento"] for record in records(log_file)]
    assert network_calls == 5
    assert events.count("FALHA_COMUNICACAO_ML") == 5
    assert events.count("CIRCUIT_BREAKER_ML") == 1


def test_indisponibilidade_em_varios_itens_preserva_todas_as_decisoes():
    network_calls = 0

    class UnavailableProvider:
        def classificar(self, observacao: str, timeout_seconds: float):
            nonlocal network_calls
            network_calls += 1
            raise ConnectionError("offline")

    classifier = ClassificadorDivergencia(
        enabled=True,
        confianca_minima=0.85,
        timeout_seconds=0.1,
        provedor=UnavailableProvider(),
    )
    recorder = MLDecisionRecorder("bot-ml", "exec-sabotagem")
    processor = ItemProcessor(
        {f"L{index:03d}" for index in range(7)},
        divergence_classifier=classifier,
        decision_recorder=recorder,
    )

    results = [processor.process(ambiguous_item(index)) for index in range(7)]

    assert network_calls == 7
    assert all(result.resultado == "REVISAO" for result in results)
    assert all(
        result.enriquecimento_ml is not None
        and result.enriquecimento_ml.motivo_fallback == "indisponibilidade"
        for result in results
    )
    assert len(recorder.decisions) == 7
    assert len({decision.lote_id for decision in recorder.decisions}) == 7
    assert all(
        decision.resultado_aplicado == "REVISAO"
        for decision in recorder.decisions
    )
