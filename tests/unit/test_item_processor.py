from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.bot import LotePerformer
from src.item_processor import (
    API_MODEL_STATUSES,
    ML_OFFLINE_RESULT,
    ItemClassification,
    ItemProcessor,
)
from src.ml_client import MLPrediction
from src.validation import HumanReviewRequired
from src.vault_client import VaultClient


pytestmark = pytest.mark.unit


def item(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "lote_id": "L001",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manha",
        "status": "EM ANALISE",
        "responsavel": "Rebecca",
        "data": "2026-07-19",
        "observacao": "Conferencia solicitada",
    }
    record.update(overrides)
    return record


def prediction(
    *,
    classe: str = "valido_automatico",
    probabilidade: float = 0.90,
    nivel_confianca: str = "alta",
    acao: str = "valido_automatico",
) -> MLPrediction:
    return MLPrediction(  # type: ignore[arg-type]
        classe=classe,
        probabilidade=probabilidade,
        nivel_confianca=nivel_confianca,
        acao=acao,
        latencia_ms=12.5,
    )


class FakeMLClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def classificar(self, **payload):
        self.calls.append(payload)
        return self.responses.pop(0)


def test_integracao_desabilitada_preserva_revisao_sem_chamar_api():
    client = FakeMLClient([prediction()])
    processor = ItemProcessor(
        {"L001"},
        ml_enabled=False,
        ml_client=client,
    )

    result = processor.process(item())

    assert result.resultado == "REVISAO"
    assert client.calls == []


def test_item_nao_ambiguo_nao_consulta_api():
    client = FakeMLClient([prediction()])
    processor = ItemProcessor({"L001"}, ml_enabled=True, ml_client=client)

    result = processor.process(item(status="APROVADO"))

    assert result.resultado == "APROVADO"
    assert client.calls == []


def test_status_fora_do_dominio_do_modelo_mantem_revisao_sem_chamada():
    client = FakeMLClient([prediction()])
    processor = ItemProcessor({"L001"}, ml_enabled=True, ml_client=client)

    result = processor.process(item(status="A REVISAR"))

    assert result.resultado == "REVISAO"
    assert client.calls == []


def test_dominio_do_cliente_reflete_status_aceitos_pela_api():
    assert API_MODEL_STATUSES == {
        "EM ANALISE",
        "AJUSTE DE LINHA",
        "ESPECIFICACAO EM REVISAO",
        "PENDENTE",
    }


@pytest.mark.parametrize("status", ["AJUSTE DE LINHA", "ESPECIFICACAO EM REVISAO"])
def test_status_do_modelo_nao_sobrepoe_resultado_deterministico(status: str):
    client = FakeMLClient([prediction()])
    processor = ItemProcessor({"L001"}, ml_enabled=True, ml_client=client)

    result = processor.process(item(status=status))

    assert result.resultado == "DIVERGENCIA"
    assert client.calls == []


class FakeDeterministicClassifier:
    def __init__(self, classification: ItemClassification):
        self.classification = classification
        self.calls = []

    def classify(self, current_item):
        self.calls.append(current_item)
        return self.classification


def test_decisao_ambiguo_de_classificador_injetado_pode_consultar_modelo():
    review = HumanReviewRequired(
        lote_id="L001",
        status_original="AJUSTE DE LINHA",
    )
    deterministic = FakeDeterministicClassifier(
        ItemClassification(
            resultado="REVISAO",
            mensagem=review.reason,
            review=review,
        )
    )
    client = FakeMLClient([prediction()])
    processor = ItemProcessor(
        ml_enabled=True,
        ml_client=client,
        deterministic_classifier=deterministic,
    )

    result = processor.process(item(status="AJUSTE DE LINHA"))

    assert result.resultado == "APROVADO"
    assert len(deterministic.calls) == 1
    assert client.calls[0]["status_raw"] == "AJUSTE DE LINHA"


def test_classificador_injetado_nao_ambiguo_impede_chamada_ao_modelo():
    deterministic = FakeDeterministicClassifier(
        ItemClassification(resultado="DIVERGENCIA", mensagem="RN05")
    )
    client = FakeMLClient([prediction()])
    processor = ItemProcessor(
        ml_enabled=True,
        ml_client=client,
        deterministic_classifier=deterministic,
    )

    result = processor.process(item())

    assert result.resultado == "DIVERGENCIA"
    assert client.calls == []


@pytest.mark.parametrize(
    ("ml_prediction", "expected_result"),
    [
        (prediction(), "APROVADO"),
        (
            prediction(
                classe="recusar_automatico",
                probabilidade=0.94,
                acao="recusar_automatico",
            ),
            "REPROVADO",
        ),
    ],
)
def test_confianca_alta_aplica_decisao_automatica(
    ml_prediction: MLPrediction,
    expected_result: str,
):
    client = FakeMLClient([ml_prediction])
    processor = ItemProcessor({"L001"}, ml_enabled=True, ml_client=client)

    result = processor.process(item())

    assert result.resultado == expected_result
    assert result.ml_prediction == ml_prediction
    assert result.ml_decision is not None
    assert result.ml_decision.resultado_aplicado == expected_result
    assert client.calls[0] == {
        "lote_id": "L001",
        "status_raw": "EM ANALISE",
        "turno": "Manha",
        "tem_obs": True,
    }


@pytest.mark.parametrize(
    "ml_prediction",
    [
        prediction(classe="revisar", acao="revisar"),
        prediction(
            probabilidade=0.70,
            nivel_confianca="media",
            acao="revisar",
        ),
        prediction(
            probabilidade=0.50,
            nivel_confianca="baixa",
            acao="revisar_prioritario",
        ),
        prediction(acao="revisar"),
    ],
)
def test_decisao_nao_automatica_permanece_em_revisao(
    ml_prediction: MLPrediction,
):
    processor = ItemProcessor(
        {"L001"},
        ml_enabled=True,
        ml_client=FakeMLClient([ml_prediction]),
    )

    result = processor.process(item())

    assert result.resultado == "REVISAO"
    assert result.review is not None
    assert result.ml_prediction == ml_prediction
    assert result.ml_decision is not None
    assert result.ml_decision.resultado_aplicado == "REVISAO"


def test_api_indisponivel_gera_revisao_ml_offline():
    processor = ItemProcessor(
        {"L001"},
        ml_enabled=True,
        ml_client=FakeMLClient([None]),
    )

    result = processor.process(item())

    assert result.resultado == ML_OFFLINE_RESULT
    assert result.review is not None
    assert "revisão humana" in result.review.reason
    assert result.ml_decision is not None
    assert result.ml_decision.classe is None
    assert result.ml_decision.probabilidade is None
    assert result.ml_decision.latencia_ms is None


class FakeQueue:
    def __init__(self, items: list[dict[str, object]]):
        self.items = items
        self.done: list[tuple[Mapping[str, object], dict[str, str]]] = []
        self.human_reviews = []
        self.ml_offline_reviews = []
        self.business_errors = []
        self.system_errors = []

    def has_next(self):
        return bool(self.items)

    def next(self):
        return self.items.pop(0)

    def mark_done(self, current_item, result):
        self.done.append((current_item, result))

    def mark_human_review(self, current_item, review, result):
        self.human_reviews.append((current_item, review, result))

    def mark_ml_offline_review(self, current_item, review, result):
        self.ml_offline_reviews.append((current_item, review, result))

    def mark_business_error(self, current_item, error, result):
        self.business_errors.append((current_item, error, result))

    def mark_system_error(self, current_item, error, result):
        self.system_errors.append((current_item, error, result))


class FakeVaultProvider:
    def get_credential(self, label):
        return {"username": "teste.erp", "password": "senha-ficticia"}


def test_performer_continua_apos_fallback_e_processa_item_seguinte():
    queue = FakeQueue([item(), item(lote_id="L002", status="APROVADO")])
    processor = ItemProcessor(
        {"L001", "L002"},
        ml_enabled=True,
        ml_client=FakeMLClient([None]),
    )
    performer = LotePerformer(
        queue,
        {"L001", "L002"},
        VaultClient(FakeVaultProvider()),
        item_processor=processor,
    )

    result = performer.run()

    assert result.total == 2
    assert result.system_errors == 0
    assert len(result.human_reviews) == 1
    assert queue.human_reviews == []
    assert (
        queue.ml_offline_reviews[0][2]["resultado_validacao"]
        == ML_OFFLINE_RESULT
    )
    assert queue.business_errors == []
    assert queue.system_errors == []
    assert len(queue.done) == 1
    assert queue.done[0][0]["lote_id"] == "L002"
    assert len(result.ml_decisions) == 1
    assert result.ml_decisions[0].resultado_aplicado == ML_OFFLINE_RESULT
