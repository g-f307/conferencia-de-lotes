"""Registro tipado e persistivel das decisoes complementares de ML."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.logging_config import LOGGER_NAME
from src.ml_client import MLPrediction

if TYPE_CHECKING:
    from src.classificador_divergencia import ResultadoClassificacaoDivergencia

LOGGER = logging.getLogger(LOGGER_NAME)
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MLDecisionAudit:
    timestamp: str
    execution_id: str
    bot_id: str
    lote_id: str
    classe: str | None
    probabilidade: float | None
    nivel_confianca: str | None
    acao: str | None
    resultado_aplicado: str
    latencia_ms: float | None

    def __post_init__(self) -> None:
        for field_name in (
            "timestamp",
            "execution_id",
            "bot_id",
            "lote_id",
            "resultado_aplicado",
        ):
            value = _required_text(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, value)

        _validate_timestamp(self.timestamp)
        for field_name in ("classe", "nivel_confianca", "acao"):
            value = _optional_text(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, value)

        probability = _optional_number(self.probabilidade, "probabilidade")
        if probability is not None and not 0 <= probability <= 1:
            raise ValueError("probabilidade deve estar entre 0 e 1")
        object.__setattr__(self, "probabilidade", probability)

        latency = _optional_number(self.latencia_ms, "latencia_ms")
        if latency is not None and latency < 0:
            raise ValueError("latencia_ms não pode ser negativa")
        object.__setattr__(self, "latencia_ms", latency)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MLDecisionAudit:
        return cls(
            timestamp=payload.get("timestamp"),
            execution_id=payload.get("execution_id"),
            bot_id=payload.get("bot_id"),
            lote_id=payload.get("lote_id"),
            classe=payload.get("classe"),
            probabilidade=payload.get("probabilidade"),
            nivel_confianca=payload.get("nivel_confianca"),
            acao=payload.get("acao"),
            resultado_aplicado=payload.get("resultado_aplicado"),
            latencia_ms=payload.get("latencia_ms"),
        )


class MLDecisionRecorder:
    """Cria o registro usado simultaneamente pelo log e pelos relatorios."""

    def __init__(
        self,
        bot_id: str,
        execution_id: str,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self.bot_id = _required_text(bot_id, "bot_id")
        self.execution_id = _required_text(execution_id, "execution_id")
        self._clock = clock
        self._decisions: list[MLDecisionAudit] = []

    @property
    def decisions(self) -> tuple[MLDecisionAudit, ...]:
        return tuple(self._decisions)

    def record_prediction(
        self,
        lote_id: str,
        prediction: MLPrediction,
        resultado_aplicado: str,
    ) -> MLDecisionAudit:
        decision = self._new_decision(
            lote_id=lote_id,
            classe=prediction.classe,
            probabilidade=prediction.probabilidade,
            nivel_confianca=prediction.nivel_confianca,
            acao=prediction.acao,
            resultado_aplicado=resultado_aplicado,
            latencia_ms=prediction.latencia_ms,
        )
        self._record(decision, evento="DECISAO_ML", status="SUCCESS")
        return decision

    def record_fallback(
        self,
        lote_id: str,
        resultado_aplicado: str,
    ) -> MLDecisionAudit:
        decision = self._new_decision(
            lote_id=lote_id,
            classe=None,
            probabilidade=None,
            nivel_confianca=None,
            acao=None,
            resultado_aplicado=resultado_aplicado,
            latencia_ms=None,
        )
        self._record(decision, evento="REVISAO_ML_OFFLINE", status="FALLBACK")
        return decision

    def record_enrichment(
        self,
        lote_id: str,
        enrichment: ResultadoClassificacaoDivergencia,
        resultado_deterministico: str,
    ) -> MLDecisionAudit:
        """Registra metadados do ML sem atribuir a ele a decisão operacional."""

        decision = self._new_decision(
            lote_id=lote_id,
            classe=enrichment.causa_provavel,
            probabilidade=enrichment.confianca_ml,
            nivel_confianca=None,
            acao=None,
            resultado_aplicado=resultado_deterministico,
            latencia_ms=enrichment.latencia_ms,
        )
        is_ml = enrichment.origem_decisao == "ml"
        self._record(
            decision,
            evento=(
                "ENRIQUECIMENTO_ML"
                if is_ml
                else "FALLBACK_CLASSIFICADOR_DIVERGENCIA"
            ),
            status="SUCCESS" if is_ml else "FALLBACK",
        )
        return decision

    def _new_decision(self, **values: Any) -> MLDecisionAudit:
        timestamp = self._clock()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return MLDecisionAudit(
            timestamp=timestamp.astimezone(timezone.utc).isoformat(),
            execution_id=self.execution_id,
            bot_id=self.bot_id,
            **values,
        )

    def _record(self, decision: MLDecisionAudit, *, evento: str, status: str) -> None:
        self._decisions.append(decision)
        LOGGER.log(
            logging.INFO if status == "SUCCESS" else logging.WARNING,
            "Decisao complementar de ML registrada para o lote %s",
            decision.lote_id,
            extra={
                "evento": evento,
                "formulario": "ItemProcessor",
                "status": status,
                "usuario": "sistema",
                "lote_id": decision.lote_id,
                "classe": decision.classe,
                "probabilidade": decision.probabilidade,
                "nivel_confianca": decision.nivel_confianca,
                "acao": decision.acao,
                "resultado_aplicado": decision.resultado_aplicado,
                "latencia_ms": decision.latencia_ms,
                "timestamp_decisao": decision.timestamp,
            },
        )


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} é obrigatório e deve ser texto não vazio")
    return value.strip()


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} deve ser texto não vazio ou nulo")
    return value.strip()


def _optional_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(  # noqa: TRY004 - preserva o contrato público existente
            f"{field_name} deve ser numérico ou nulo"
        )
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{field_name} deve ser finito")
    return converted


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("timestamp deve estar no formato ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp deve incluir fuso horário")
