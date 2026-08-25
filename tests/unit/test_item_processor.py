from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.bot import LotePerformer
from src.classificador_divergencia import ResultadoClassificacaoDivergencia
from src.item_processor import ItemClassification, ItemProcessor
from src.ml_audit import MLDecisionRecorder
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


def enrichment(
    *,
    causa: str = "falha_de_calibracao",
    confianca: float | None = 0.99,
    origem: str = "ml",
    motivo: str | None = None,
) -> ResultadoClassificacaoDivergencia:
    return ResultadoClassificacaoDivergencia(  # type: ignore[arg-type]
        causa_provavel=causa,
        confianca_ml=confianca,
        origem_decisao=origem,
        motivo_fallback=motivo,
        latencia_ms=12.5,
    )


class FakeDivergenceClassifier:
    def __init__(self, response: ResultadoClassificacaoDivergencia):
        self.response = response
        self.calls: list[str | None] = []

    def classificar(self, observacao: str | None):
        self.calls.append(observacao)
        return self.response


class FailingClassifier:
    def classificar(self, observacao: str | None):
        raise RuntimeError("segredo-do-provedor")


class FakeDeterministicClassifier:
    def __init__(self, classification: ItemClassification):
        self.classification = classification
        self.calls: list[Mapping[str, object]] = []

    def classify(self, current_item: Mapping[str, object]):
        self.calls.append(current_item)
        return self.classification


def decision_recorder() -> MLDecisionRecorder:
    return MLDecisionRecorder("bot-test", "exec-test")


def test_item_valido_nao_consulta_ml():
    classifier = FakeDivergenceClassifier(enrichment())
    processor = ItemProcessor(
        {"L001"},
        divergence_classifier=classifier,
    )

    result = processor.process(item(status="APROVADO"))

    assert result.resultado == "APROVADO"
    assert result.enriquecimento_ml is None
    assert classifier.calls == []


@pytest.mark.parametrize("resultado", ["DIVERGENCIA", "REPROVADO", "REVISAO"])
def test_ml_apenas_enriquece_e_preserva_decisao_das_regras(resultado: str):
    review = (
        HumanReviewRequired("L001", "EM ANALISE")
        if resultado == "REVISAO"
        else None
    )
    deterministic_result = ItemClassification(
        resultado=resultado,
        mensagem=f"resultado deterministico {resultado}",
        validated={"status": resultado},
        review=review,
    )
    deterministic = FakeDeterministicClassifier(deterministic_result)
    classifier = FakeDivergenceClassifier(enrichment(confianca=1.0))
    processor = ItemProcessor(
        deterministic_classifier=deterministic,
        divergence_classifier=classifier,
        decision_recorder=decision_recorder(),
    )

    result = processor.process(item())

    assert result.resultado == deterministic_result.resultado
    assert result.mensagem == deterministic_result.mensagem
    assert result.validated == deterministic_result.validated
    assert result.review == deterministic_result.review
    assert result.enriquecimento_ml == classifier.response
    assert result.ml_decision is not None
    assert result.ml_decision.resultado_aplicado == resultado
    assert classifier.calls == ["Conferencia solicitada"]
    assert len(deterministic.calls) == 1


@pytest.mark.parametrize(
    ("origem", "motivo"),
    [
        ("fallback", "timeout"),
        ("fallback", "baixa_confianca"),
        ("fallback", "indisponibilidade"),
        ("fallback", "observacao_ausente"),
    ],
)
def test_fallback_do_ml_nao_altera_revisao(origem: str, motivo: str):
    review = HumanReviewRequired("L001", "EM ANALISE")
    deterministic = ItemClassification(
        resultado="REVISAO",
        mensagem=review.reason,
        review=review,
    )
    classifier = FakeDivergenceClassifier(
        enrichment(
            causa="nao_classificado",
            confianca=None,
            origem=origem,
            motivo=motivo,
        )
    )
    processor = ItemProcessor(
        deterministic_classifier=FakeDeterministicClassifier(deterministic),
        divergence_classifier=classifier,
    )

    result = processor.process(item())

    assert result.resultado == "REVISAO"
    assert result.review == review
    assert result.mensagem == deterministic.mensagem
    assert result.enriquecimento_ml == classifier.response


def test_excecao_de_classificador_injetado_nao_interrompe_nem_altera_regras():
    deterministic = ItemClassification(
        resultado="DIVERGENCIA",
        mensagem="RN05: lote inexistente",
    )
    processor = ItemProcessor(
        deterministic_classifier=FakeDeterministicClassifier(deterministic),
        divergence_classifier=FailingClassifier(),
    )

    result = processor.process(item())

    assert result.resultado == deterministic.resultado
    assert result.mensagem == deterministic.mensagem
    assert result.enriquecimento_ml is not None
    assert result.enriquecimento_ml.causa_provavel == "nao_classificado"
    assert result.enriquecimento_ml.origem_decisao == "fallback"
    assert result.enriquecimento_ml.motivo_fallback == "indisponibilidade"


def test_regras_sao_executadas_antes_do_enriquecimento_ml():
    events: list[str] = []

    class OrderedDeterministicClassifier:
        def classify(self, current_item):
            events.append("regras")
            return ItemClassification(
                resultado="DIVERGENCIA",
                mensagem="RN05: lote inexistente",
            )

    class OrderedDivergenceClassifier:
        def classificar(self, observacao):
            events.append("ml")
            return enrichment()

    processor = ItemProcessor(
        deterministic_classifier=OrderedDeterministicClassifier(),
        divergence_classifier=OrderedDivergenceClassifier(),
    )

    result = processor.process(item())

    assert events == ["regras", "ml"]
    assert result.resultado == "DIVERGENCIA"


def test_classificador_padrao_desabilitado_mantem_status_deterministico():
    processor = ItemProcessor({"L001"})

    result = processor.process(item())

    assert result.resultado == "REVISAO"
    assert result.enriquecimento_ml is not None
    assert result.enriquecimento_ml.origem_decisao == "fallback"
    assert result.enriquecimento_ml.motivo_fallback == "ml_desabilitado"


class FakeQueue:
    def __init__(self, items: list[dict[str, object]]):
        self.items = items
        self.done: list[tuple[Mapping[str, object], dict[str, str]]] = []
        self.human_reviews = []
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

    def mark_business_error(self, current_item, error, result):
        self.business_errors.append((current_item, error, result))

    def mark_system_error(self, current_item, error, result):
        self.system_errors.append((current_item, error, result))


class FakeVaultProvider:
    def get_credential(self, label):
        return {"username": "teste.erp", "password": "senha-ficticia"}


def test_performer_mantem_revisao_apos_fallback_e_processa_item_seguinte():
    queue = FakeQueue([item(), item(lote_id="L002", status="APROVADO")])
    classifier = FakeDivergenceClassifier(
        enrichment(
            causa="nao_classificado",
            confianca=None,
            origem="fallback",
            motivo="timeout",
        )
    )
    recorder = decision_recorder()
    processor = ItemProcessor(
        {"L001", "L002"},
        divergence_classifier=classifier,
        decision_recorder=recorder,
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
    assert queue.human_reviews[0][2]["resultado_validacao"] == "REVISAO"
    assert queue.business_errors == []
    assert queue.system_errors == []
    assert len(queue.done) == 1
    assert queue.done[0][0]["lote_id"] == "L002"
    assert len(result.ml_decisions) == 1
    assert result.ml_decisions[0].resultado_aplicado == "REVISAO"


def test_item_divergente_publica_a_mesma_auditoria_no_datapool():
    queue = FakeQueue([item(produto="")])
    classifier = FakeDivergenceClassifier(enrichment(confianca=0.97))
    recorder = decision_recorder()
    processor = ItemProcessor(
        {"L001"},
        divergence_classifier=classifier,
        decision_recorder=recorder,
    )
    performer = LotePerformer(
        queue,
        {"L001"},
        VaultClient(FakeVaultProvider()),
        item_processor=processor,
    )

    result = performer.run()

    assert result.business_errors == 1
    assert len(result.ml_decisions) == 1
    output = queue.business_errors[0][2]
    decision = result.ml_decisions[0]
    assert output["resultado_validacao"] == "DIVERGENCIA"
    assert output["causa_provavel"] == decision.causa_provavel
    assert output["origem_decisao"] == decision.origem_decisao == "ml"
    assert output["confianca_ml"] == str(decision.confianca_ml)
    assert output["motivo_fallback"] == ""
