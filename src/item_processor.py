"""Decisão determinística e enriquecimento de ML para itens do DataPool."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol

from src.classificador_divergencia import (
    ClassificadorDivergencia,
    ResultadoClassificacaoDivergencia,
)
from src.ml_audit import MLDecisionAudit, MLDecisionRecorder
from src.validation import (
    HumanReviewRequired,
    HumanReviewStatus,
    ValidationError,
    validate_lote,
)

ML_ENRICHMENT_RESULTS = frozenset({"DIVERGENCIA", "REPROVADO", "REVISAO"})


class DivergenceClassifier(Protocol):
    """Fronteira que impede o provedor de ML de decidir o status do item."""

    def classificar(
        self,
        observacao: str | None,
    ) -> ResultadoClassificacaoDivergencia: ...


@dataclass(frozen=True)
class ItemClassification:
    resultado: str
    mensagem: str
    validated: dict[str, str] = field(default_factory=dict)
    review: HumanReviewRequired | None = None
    enriquecimento_ml: ResultadoClassificacaoDivergencia | None = None
    ml_decision: MLDecisionAudit | None = None


class DeterministicClassifier(Protocol):
    """Contrato da primeira camada, sem acoplar o ML às regras de negócio."""

    def classify(self, item: Mapping[str, object]) -> ItemClassification: ...


class OperationalItemClassifier:
    """Preserva a classificação RN01-RN07 usada pelo Performer."""

    def __init__(self, reference_lotes: Iterable[str]) -> None:
        self.reference_lotes = tuple(reference_lotes)

    def classify(self, item: Mapping[str, object]) -> ItemClassification:
        try:
            validated = validate_lote(item, self.reference_lotes)
        except HumanReviewStatus as exc:
            review = HumanReviewRequired(
                lote_id=str(item.get("lote_id") or "").strip(),
                status_original=exc.status,
            )
            return ItemClassification(
                resultado="REVISAO",
                mensagem=review.reason,
                review=review,
            )
        except ValidationError as exc:
            return ItemClassification(
                resultado="DIVERGENCIA",
                mensagem=str(exc),
            )

        if validated["status"] == "REPROVADO":
            observation = validated.get("observacao") or "Divergência registrada"
            return ItemClassification(
                resultado="REPROVADO",
                mensagem=f"Lote reprovado: {observation}",
                validated=validated,
            )

        return ItemClassification(
            resultado="APROVADO",
            mensagem="Lote aprovado pelas regras RN01–RN07",
            validated=validated,
        )


class ItemProcessor:
    """Executa as regras antes do ML e preserva integralmente sua decisão."""

    def __init__(
        self,
        reference_lotes: Iterable[str] | None = None,
        *,
        divergence_classifier: DivergenceClassifier | None = None,
        deterministic_classifier: DeterministicClassifier | None = None,
        decision_recorder: MLDecisionRecorder | None = None,
    ) -> None:
        if deterministic_classifier is None:
            if reference_lotes is None:
                raise ValueError(
                    "Lotes de referência ou classificador determinístico devem ser informados"
                )
            deterministic_classifier = OperationalItemClassifier(reference_lotes)

        self.deterministic_classifier = deterministic_classifier
        self.divergence_classifier = divergence_classifier or ClassificadorDivergencia(
            enabled=False,
            confianca_minima=0.85,
            timeout_seconds=3.0,
        )
        self.decision_recorder = decision_recorder

    def process(self, item: Mapping[str, object]) -> ItemClassification:
        deterministic = self.deterministic_classifier.classify(item)
        if deterministic.resultado not in ML_ENRICHMENT_RESULTS:
            return deterministic

        return self._enrich_without_changing_status(item, deterministic)

    def _enrich_without_changing_status(
        self,
        item: Mapping[str, object],
        deterministic: ItemClassification,
    ) -> ItemClassification:
        try:
            enrichment = self.divergence_classifier.classificar(
                str(item.get("observacao") or "").strip()
            )
        except Exception:  # noqa: BLE001 - fronteira externa deve falhar com segurança
            # Até uma implementação externa fora do contrato deve falhar de modo seguro.
            return deterministic

        decision = None
        if self.decision_recorder is not None:
            decision = self.decision_recorder.record_enrichment(
                str(item.get("lote_id") or "").strip(),
                enrichment,
                deterministic.resultado,
            )

        return replace(
            deterministic,
            enriquecimento_ml=enrichment,
            ml_decision=decision,
        )
