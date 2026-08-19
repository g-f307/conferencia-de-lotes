"""Decisão determinística e complemento de ML para cada item do DataPool."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Iterable, Mapping, Protocol

from src.logging_config import LOGGER_NAME
from src.ml_client import MLPrediction
from src.validation import (
    HumanReviewRequired,
    HumanReviewStatus,
    ValidationError,
    normalize_status,
    validate_lote,
)


LOGGER = logging.getLogger(LOGGER_NAME)
ML_OFFLINE_RESULT = "REVISAO_ML_OFFLINE"
API_MODEL_STATUSES = frozenset(
    {
        "EM ANALISE",
        "AJUSTE DE LINHA",
        "ESPECIFICACAO EM REVISAO",
        "PENDENTE",
    }
)


class PredictionClient(Protocol):
    def classificar(
        self,
        *,
        lote_id: str,
        status_raw: str,
        turno: str,
        tem_obs: bool,
    ) -> MLPrediction | None: ...


@dataclass(frozen=True)
class ItemClassification:
    resultado: str
    mensagem: str
    validated: dict[str, str] = field(default_factory=dict)
    review: HumanReviewRequired | None = None
    ml_prediction: MLPrediction | None = None


class DeterministicClassifier(Protocol):
    """Contrato da primeira camada, sem acoplar o ML a uma família de regras."""

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
    """Complementa somente decisões ambíguas produzidas pela primeira camada."""

    def __init__(
        self,
        reference_lotes: Iterable[str] | None = None,
        *,
        ml_enabled: bool = False,
        ml_client: PredictionClient | None = None,
        deterministic_classifier: DeterministicClassifier | None = None,
    ) -> None:
        if ml_enabled and ml_client is None:
            raise ValueError("MLClient deve ser informado quando ML está habilitado")
        if deterministic_classifier is None:
            if reference_lotes is None:
                raise ValueError(
                    "Lotes de referência ou classificador determinístico devem ser informados"
                )
            deterministic_classifier = OperationalItemClassifier(reference_lotes)
        self.deterministic_classifier = deterministic_classifier
        self.ml_enabled = ml_enabled
        self.ml_client = ml_client

    def process(self, item: Mapping[str, object]) -> ItemClassification:
        deterministic = self.deterministic_classifier.classify(item)
        if deterministic.resultado != "REVISAO" or deterministic.review is None:
            return deterministic

        status = normalize_status(deterministic.review.status_original)
        if not self.ml_enabled or status not in API_MODEL_STATUSES:
            return deterministic
        return self._apply_ml(item, deterministic)

    def _apply_ml(
        self,
        item: Mapping[str, object],
        deterministic_review: ItemClassification,
    ) -> ItemClassification:
        assert self.ml_client is not None
        lote_id = str(item.get("lote_id") or "").strip()
        prediction = self.ml_client.classificar(
            lote_id=lote_id,
            status_raw=str(item.get("status") or "").strip(),
            turno=str(item.get("turno") or "").strip(),
            tem_obs=bool(str(item.get("observacao") or "").strip()),
        )
        if prediction is None:
            review = HumanReviewRequired(
                lote_id=lote_id,
                status_original=str(item.get("status") or "").strip(),
                reason="API ML indisponível; lote encaminhado para revisão humana",
            )
            LOGGER.warning(
                "Fallback de revisão humana aplicado por indisponibilidade da API ML",
                extra={
                    "evento": "REVISAO_ML_OFFLINE",
                    "formulario": "ItemProcessor",
                    "status": "FALLBACK",
                    "usuario": "sistema",
                    "lote_id": lote_id,
                    "classe": ML_OFFLINE_RESULT,
                    "acao": "revisar",
                },
            )
            return ItemClassification(
                resultado=ML_OFFLINE_RESULT,
                mensagem=review.reason,
                review=review,
            )

        if self._is_high_confidence_action(
            prediction,
            "valido_automatico",
        ):
            return ItemClassification(
                resultado="APROVADO",
                mensagem="Lote aprovado por decisão complementar de ML",
                ml_prediction=prediction,
            )
        if self._is_high_confidence_action(
            prediction,
            "recusar_automatico",
        ):
            return ItemClassification(
                resultado="REPROVADO",
                mensagem="Lote reprovado por decisão complementar de ML",
                ml_prediction=prediction,
            )

        return ItemClassification(
            resultado=deterministic_review.resultado,
            mensagem="Decisão de ML mantida em revisão humana",
            review=deterministic_review.review,
            ml_prediction=prediction,
        )

    @staticmethod
    def _is_high_confidence_action(
        prediction: MLPrediction,
        automatic_action: str,
    ) -> bool:
        return (
            prediction.nivel_confianca == "alta"
            and prediction.probabilidade >= 0.85
            and prediction.classe == automatic_action
            and prediction.acao == automatic_action
        )
