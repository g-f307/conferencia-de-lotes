"""Registro tipado e persistivel das decisoes complementares de ML."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Mapping

from src.logging_config import LOGGER_NAME
from src.ml_client import MLPrediction


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MLDecisionAudit":
        probability = payload.get("probabilidade")
        latency = payload.get("latencia_ms")
        return cls(
            timestamp=str(payload.get("timestamp") or ""),
            execution_id=str(payload.get("execution_id") or ""),
            bot_id=str(payload.get("bot_id") or ""),
            lote_id=str(payload.get("lote_id") or ""),
            classe=_optional_text(payload.get("classe")),
            probabilidade=None if probability is None else float(probability),
            nivel_confianca=_optional_text(payload.get("nivel_confianca")),
            acao=_optional_text(payload.get("acao")),
            resultado_aplicado=str(payload.get("resultado_aplicado") or ""),
            latencia_ms=None if latency is None else float(latency),
        )


class MLDecisionRecorder:
    """Cria o registro usado simultaneamente pelo log e pelos relatorios."""

    def __init__(
        self,
        bot_id: str = "",
        execution_id: str = "",
        *,
        clock: Clock = utc_now,
    ) -> None:
        self.bot_id = bot_id
        self.execution_id = execution_id
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


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)
