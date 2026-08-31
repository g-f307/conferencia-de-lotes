"""Serviço final de relatórios e alertas do pipeline híbrido."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.alerts import Alerta, Severidade, SistemaAlertas
from src.logging_config import LOGGER_NAME

from .models import (
    REPORT_TYPE_BUSINESS,
    REPORT_TYPE_INCIDENT,
    HybridReportSnapshot,
    build_report_snapshot,
    describe_fallback,
)
from .renderers import (
    write_capstone_excel,
    write_capstone_markdown,
    write_capstone_pdf,
)

REPORT_BOT_ID = "relatorio-alertas-v2"
ML_UNAVAILABLE_REASONS = frozenset(
    {"indisponibilidade", "timeout", "resposta_invalida"}
)


@dataclass(frozen=True)
class CapstoneReportPaths:
    summary: Path
    markdown: Path
    pdf: Path
    excel: Path | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "summary": self.summary.as_posix(),
            "markdown": self.markdown.as_posix(),
            "pdf": self.pdf.as_posix(),
            "excel": self.excel.as_posix() if self.excel else None,
        }


@dataclass(frozen=True)
class NotificationAttempt:
    evento: str
    entregues: tuple[str, ...]
    falhos: tuple[str, ...]
    status: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entregues"] = list(self.entregues)
        payload["falhos"] = list(self.falhos)
        return payload


@dataclass(frozen=True)
class CapstoneReportResult:
    snapshot: HybridReportSnapshot
    paths: CapstoneReportPaths
    notification_results: tuple[NotificationAttempt, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.snapshot.to_dict(),
            "report_paths": self.paths.to_dict(),
            "summary_path": self.paths.summary.as_posix(),
            "notification_results": [
                result.to_dict() for result in self.notification_results
            ],
        }


class CapstoneReportService:
    """Materializa os artefatos sem reler fontes nem recalcular regras."""

    def __init__(
        self,
        output_dir: Path,
        *,
        alerts: SistemaAlertas | None = None,
        degraded_alert_seconds: float = 300.0,
        logger: logging.Logger | None = None,
    ) -> None:
        if degraded_alert_seconds < 0:
            raise ValueError("degraded_alert_seconds não pode ser negativo")
        self.output_dir = Path(output_dir)
        self.alerts = alerts
        self.degraded_alert_seconds = degraded_alert_seconds
        self.logger = logger or logging.getLogger(LOGGER_NAME)

    def generate(self, payload: Mapping[str, Any]) -> CapstoneReportResult:
        snapshot = build_report_snapshot(payload)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        paths = CapstoneReportPaths(
            summary=self.output_dir / "resumo_pipeline_hibrido.json",
            markdown=self.output_dir / "resumo_pipeline_hibrido.md",
            pdf=self.output_dir / "relatorio_pipeline_hibrido.pdf",
            excel=(
                self.output_dir / "relatorio_pipeline_hibrido.xlsx"
                if snapshot.report_type == REPORT_TYPE_BUSINESS
                else None
            ),
        )

        write_capstone_markdown(snapshot, paths.markdown)
        write_capstone_pdf(snapshot, paths.pdf)
        if paths.excel is not None:
            write_capstone_excel(snapshot, paths.excel)

        attachment = paths.excel or paths.pdf
        alerts = build_capstone_alerts(
            snapshot,
            attachment,
            degraded_alert_seconds=self.degraded_alert_seconds,
        )
        notification_results = self._notify(alerts)
        result = CapstoneReportResult(snapshot, paths, notification_results)
        _write_json_atomic(paths.summary, result.to_dict())
        self.logger.info(
            "Relatório Capstone concluído execution_id=%s report_type=%s status=%s",
            snapshot.execution_id,
            snapshot.report_type,
            snapshot.status,
            extra={
                "evento": "RELATORIO_CAPSTONE",
                "formulario": "RelatorioAlertas",
                "status": "SUCCESS",
                "usuario": "sistema",
            },
        )
        return result

    def _notify(self, alerts: tuple[Alerta, ...]) -> tuple[NotificationAttempt, ...]:
        if self.alerts is None:
            return tuple(
                NotificationAttempt(alert.evento, (), (), "NOT_CONFIGURED")
                for alert in alerts
            )

        results: list[NotificationAttempt] = []
        for alert in alerts:
            try:
                delivery = self.alerts.notificar(alert)
            except Exception as exc:
                self.logger.exception(
                    "Falha inesperada no sistema de alertas (%s)",
                    type(exc).__name__,
                    extra={
                        "evento": "FALHA_SISTEMA_ALERTAS_CAPSTONE",
                        "formulario": "RelatorioAlertas",
                        "status": "FAILED",
                        "usuario": "sistema",
                    },
                )
                results.append(
                    NotificationAttempt(alert.evento, (), ("sistema_alertas",), "FAILED")
                )
                continue
            results.append(
                NotificationAttempt(
                    alert.evento,
                    delivery.entregues,
                    delivery.falhos,
                    "DELIVERED" if delivery.entregues else "FAILED",
                )
            )
        return tuple(results)


def build_capstone_alerts(
    snapshot: HybridReportSnapshot,
    attachment: Path,
    *,
    degraded_alert_seconds: float,
) -> tuple[Alerta, ...]:
    """Converte estados controlados nos cinco alertas definidos pela issue."""
    alerts: list[Alerta] = []

    def add(
        severity: Severidade,
        event: str,
        quantity: int,
        reason: str,
    ) -> None:
        alerts.append(
            Alerta(
                severidade=severity,
                execution_id=snapshot.execution_id,
                bot_id=REPORT_BOT_ID,
                quantidade_afetada=max(0, quantity),
                motivo_predominante=reason,
                estado_pipeline=snapshot.status,
                evento=event,
                anexo=attachment,
            )
        )

    if snapshot.report_type == REPORT_TYPE_INCIDENT or snapshot.status == "FAILED":
        add(
            Severidade.CRITICO,
            "execucao_critica",
            snapshot.total_items,
            describe_fallback(snapshot.failure_code or "falha_operacional"),
        )

    if (
        snapshot.modo_degradado
        and snapshot.degraded_duration_seconds >= degraded_alert_seconds
    ):
        add(
            Severidade.AVISO,
            "modo_degradado_prolongado",
            snapshot.review_items or snapshot.total_items,
            describe_fallback(snapshot.motivo_fallback or "pipeline_degradado"),
        )

    ml_fallback_items = [
        item
        for item in snapshot.items
        if item.motivo_fallback in ML_UNAVAILABLE_REASONS
    ]
    if snapshot.ml_status in {"FAILED", "TIMEOUT", "UNAVAILABLE"} or ml_fallback_items:
        add(
            Severidade.AVISO,
            "ml_indisponivel",
            len(ml_fallback_items) or snapshot.total_items,
            (
                describe_fallback(ml_fallback_items[0].motivo_fallback)
                if ml_fallback_items
                else describe_fallback("indisponibilidade")
            ),
        )

    desktop_status = _status_by_alias(
        snapshot,
        "desktop",
        "estoque",
        "estoque-desktop-v1",
    )
    if desktop_status == "UNAVAILABLE":
        add(
            Severidade.ERRO,
            "desktop_indisponivel",
            snapshot.review_items or snapshot.total_items,
            describe_fallback("desktop_unavailable_after_retry"),
        )

    if snapshot.dead_letter_produced:
        add(
            Severidade.ERRO,
            "dead_letter_produzido",
            snapshot.failed_items or 1,
            "item_irrecuperavel",
        )

    return tuple(alerts)


def _status_by_alias(snapshot: HybridReportSnapshot, *aliases: str) -> str:
    statuses = {key.casefold(): value for key, value in snapshot.source_statuses.items()}
    for alias in aliases:
        if alias.casefold() in statuses:
            return statuses[alias.casefold()]
    return "UNAVAILABLE"


def _write_json_atomic(destination: Path, payload: Mapping[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(destination)


__all__ = [
    "REPORT_BOT_ID",
    "CapstoneReportPaths",
    "CapstoneReportResult",
    "CapstoneReportService",
    "NotificationAttempt",
    "build_capstone_alerts",
]
