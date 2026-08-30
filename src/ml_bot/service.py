"""Execução independente e não crítica do classificador de divergências."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from src.classificador_divergencia import (
    ClassificadorDivergencia,
    MotivoFallback,
    ResultadoClassificacaoDivergencia,
)
from src.config import Settings
from src.consolidation import STATUS_DIVERGENCIA
from src.ml_audit import MLDecisionAudit, MLDecisionRecorder

from .models import MLBotContext

ML_BOT_ID = "classificador-ml-v1"
SCHEMA_VERSION = "1.0"
TERMINAL_DEGRADED_REASONS = frozenset(
    {
        "indisponibilidade",
        "timeout",
        "baixa_confianca",
        "resposta_invalida",
        "observacao_ausente",
    }
)


class DivergenceClassifier(Protocol):
    def classificar(
        self,
        observacao: str | None,
    ) -> ResultadoClassificacaoDivergencia: ...


class MLBotInputError(ValueError):
    """O resultado da consolidação não respeita o contrato de entrada."""


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise MLBotInputError(f"{field_name} deve ser informado")
    return normalized


def _records_from_consolidation(
    consolidation_result: Mapping[str, object],
) -> list[Mapping[str, object]]:
    payload = consolidation_result.get("payload")
    if not isinstance(payload, Mapping):
        raise MLBotInputError("payload da consolidação deve ser um objeto")
    records = payload.get("records")
    if not isinstance(records, list):
        raise MLBotInputError("payload.records da consolidação deve ser uma lista")
    if not all(isinstance(record, Mapping) for record in records):
        raise MLBotInputError("cada registro consolidado deve ser um objeto")
    return records


def _observation(record: Mapping[str, object]) -> str:
    direct = str(record.get("observacao") or "").strip()
    if direct:
        return direct
    validation = record.get("validacao")
    if not isinstance(validation, Mapping):
        return ""
    original = validation.get("campos_originais")
    if not isinstance(original, Mapping):
        return ""
    return str(original.get("observacao") or "").strip()


def _safe_fallback(
    reason: MotivoFallback = "indisponibilidade",
) -> ResultadoClassificacaoDivergencia:
    return ResultadoClassificacaoDivergencia(
        causa_provavel="nao_classificado",
        confianca_ml=None,
        origem_decisao="fallback",
        motivo_fallback=reason,
        latencia_ms=0.0,
    )


class MLBotService:
    """Enriquece divergências sem permitir que o ML altere o status recebido."""

    def __init__(
        self,
        classifier: DivergenceClassifier,
        recorder: MLDecisionRecorder,
    ) -> None:
        self.classifier = classifier
        self.recorder = recorder

    def process(
        self,
        consolidation_result: Mapping[str, object],
        context: MLBotContext,
    ) -> dict[str, Any]:
        records = _records_from_consolidation(consolidation_result)
        item_results: list[dict[str, Any]] = []
        decisions: list[MLDecisionAudit] = []

        for record in records:
            lote_id = _required_text(record.get("lote_id"), "lote_id")
            deterministic_status = _required_text(
                record.get("status_operacional"),
                "status_operacional",
            )
            eligible = deterministic_status == STATUS_DIVERGENCIA
            decision = None
            if eligible:
                enrichment = self._classify_safely(_observation(record))
                decision = self.recorder.record_enrichment(
                    lote_id,
                    enrichment,
                    deterministic_status,
                )
                decisions.append(decision)

            item_results.append(
                {
                    "lote_id": lote_id,
                    "resultado_deterministico": deterministic_status,
                    "elegivel": eligible,
                    "decisao_ml": decision.to_dict() if decision else None,
                }
            )

        fallback_reasons = {
            decision.motivo_fallback
            for decision in decisions
            if decision.motivo_fallback is not None
        }
        degraded = bool(fallback_reasons.intersection(TERMINAL_DEGRADED_REASONS))
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "PARTIALLY_COMPLETED" if degraded else "SUCCESS",
            "bot_id": ML_BOT_ID,
            "execution_id": context.execution_id,
            "correlation_id": context.correlation_id,
            "root_task_id": context.root_task_id,
            "task_id": context.task_id,
            "parent_task_id": context.parent_task_id,
            "predecessor_task_ids": list(context.predecessor_task_ids),
            "origem_dados": ["consolidacao-v2"],
            "modo_degradado": degraded,
            "motivo_fallback": self._aggregate_fallback(fallback_reasons),
            "payload": {
                "records": item_results,
                "ml_decisions": [decision.to_dict() for decision in decisions],
                "total_items": len(records),
                "eligible_items": len(decisions),
                "skipped_items": len(records) - len(decisions),
                "fallback_items": sum(
                    decision.origem_decisao == "fallback" for decision in decisions
                ),
            },
        }

    def _classify_safely(self, observation: str) -> ResultadoClassificacaoDivergencia:
        try:
            result = self.classifier.classificar(observation)
            if not isinstance(result, ResultadoClassificacaoDivergencia):
                return _safe_fallback("resposta_invalida")
            return result
        except Exception:  # noqa: BLE001 - etapa opcional nunca interrompe o pipeline
            return _safe_fallback()

    @staticmethod
    def _aggregate_fallback(reasons: set[str]) -> str | None:
        if not reasons:
            return None
        if len(reasons) == 1:
            return next(iter(reasons))
        return "multiplos_fallbacks"


def write_ml_bot_result(result: Mapping[str, object], destination: Path) -> None:
    """Persiste o envelope de forma atômica para a próxima etapa."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(destination)


def build_service_from_settings(settings: Settings) -> MLBotService:
    """Fábrica mantida pequena para o ponto de entrada e os testes de integração."""
    classifier = ClassificadorDivergencia.from_settings(settings)
    recorder = MLDecisionRecorder(ML_BOT_ID, str(settings.execution_id))
    return MLBotService(classifier, recorder)
