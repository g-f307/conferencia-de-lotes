"""Coletor resiliente do estoque exibido pelo simulador desktop."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.desktop_stock.driver import DesktopAutomationError, DesktopDriver
from src.desktop_stock.models import DesktopCollectionContext, StockRecord
from src.retry_policy import LinearRetryPolicy, RetryExhaustedError

EXPECTED_COLUMNS = (
    "lote_id",
    "produto",
    "quantidade_disponivel",
    "localizacao",
    "status_estoque",
    "atualizado_em",
)


def parse_visible_stock(text: str) -> list[StockRecord]:
    """Converte o TSV copiado da interface sem acessar a massa do simulador."""
    rows = csv.DictReader(io.StringIO(text.strip()), delimiter="\t")
    if rows.fieldnames != list(EXPECTED_COLUMNS):
        raise DesktopAutomationError("cabeçalho visual do estoque é inválido")

    records: list[StockRecord] = []
    for row_number, row in enumerate(rows, start=2):
        try:
            quantity = int(row["quantidade_disponivel"])
            if quantity < 0:
                raise ValueError
            values = {column: (row[column] or "").strip() for column in EXPECTED_COLUMNS}
            if any(not values[column] for column in EXPECTED_COLUMNS if column != "quantidade_disponivel"):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise DesktopAutomationError(
                f"registro visual inválido na linha {row_number}"
            ) from exc
        records.append(
            StockRecord(
                lote_id=values["lote_id"],
                produto=values["produto"],
                quantidade_disponivel=quantity,
                localizacao=values["localizacao"],
                status_estoque=values["status_estoque"],
                atualizado_em=values["atualizado_em"],
            )
        )
    return records


class DesktopStockCollector:
    """Executa coleta visual com retry, evidência e fallback terminal seguro."""

    def __init__(
        self,
        driver: DesktopDriver,
        retry_policy: LinearRetryPolicy,
        *,
        evidence_dir: Path,
        logger: logging.Logger | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.driver = driver
        self.retry_policy = retry_policy
        self.evidence_dir = evidence_dir
        self.logger = logger or logging.getLogger("auditor_lotes.desktop")
        self.clock = clock
        self.now = now

    def collect(self, context: DesktopCollectionContext) -> dict[str, Any]:
        started = self.clock()
        evidence_paths: list[str] = []
        attempt_number = 0
        self._log("DESKTOP_COLLECTION_STARTED", context, status="RUNNING", attempts=0)

        def operation(timeout_seconds: float) -> list[StockRecord]:
            nonlocal attempt_number
            attempt_number += 1
            self._log(
                "DESKTOP_COLLECTION_ATTEMPT",
                context,
                status="RUNNING",
                attempts=attempt_number,
            )
            try:
                self.driver.wait_until_ready(timeout_seconds)
                self.driver.search("*", timeout_seconds)
                records = parse_visible_stock(
                    self.driver.read_visible_records(timeout_seconds)
                )
                evidence = self.driver.capture_evidence(
                    self.evidence_dir
                    / f"{context.execution_id}-desktop-attempt-{attempt_number}.png"
                )
            except DesktopAutomationError:
                self._capture_attempt_evidence(
                    context,
                    attempt_number,
                    evidence_paths,
                )
                raise
            evidence_paths.append(str(evidence))
            return records

        try:
            result = self.retry_policy.execute(
                operation,
                retry_on=(DesktopAutomationError,),
            )
        except RetryExhaustedError as exc:
            self._capture_failure_evidence(context, evidence_paths)
            envelope = self._envelope(
                context,
                status="PARTIALLY_COMPLETED",
                source_status="UNAVAILABLE",
                records=[],
                attempts=exc.attempts,
                latency_ms=self._latency_ms(started),
                evidence_paths=evidence_paths,
                motivo_fallback="desktop_unavailable_after_retry",
                failure_message=self._safe_error(exc.last_error),
            )
            self._log(
                "DESKTOP_COLLECTION_FALLBACK",
                context,
                status="PARTIALLY_COMPLETED",
                attempts=exc.attempts,
                latency_ms=envelope["payload"]["latency_ms"],
                motivo_fallback="desktop_unavailable_after_retry",
                failed_items=envelope["payload"]["failed_items"],
                source_status="UNAVAILABLE",
            )
            return envelope
        finally:
            self._close_driver(context)

        envelope = self._envelope(
            context,
            status="SUCCESS",
            source_status="AVAILABLE",
            records=result.value,
            attempts=result.attempts,
            latency_ms=self._latency_ms(started),
            evidence_paths=evidence_paths,
            motivo_fallback=None,
            failure_message=None,
        )
        self._log(
            "DESKTOP_COLLECTION_FINISHED",
            context,
            status="SUCCESS",
            attempts=result.attempts,
            latency_ms=envelope["payload"]["latency_ms"],
            collected_items=len(result.value),
            failed_items=0,
            source_status="AVAILABLE",
        )
        return envelope

    def _envelope(
        self,
        context: DesktopCollectionContext,
        *,
        status: str,
        source_status: str,
        records: list[StockRecord],
        attempts: int,
        latency_ms: int,
        evidence_paths: list[str],
        motivo_fallback: str | None,
        failure_message: str | None,
    ) -> dict[str, Any]:
        artifacts = [
            {
                "name": Path(path).name,
                "type": "image/png",
                "path": path,
                "checksum_sha256": self._checksum(Path(path)),
            }
            for path in evidence_paths
            if Path(path).is_file()
        ]
        failed_items = 0 if status == "SUCCESS" else (context.expected_items or 0)
        return {
            "schema_version": "1.0",
            "execution_id": context.execution_id,
            "correlation_id": context.correlation_id,
            "root_task_id": context.root_task_id,
            "task_id": context.task_id,
            "parent_task_id": context.parent_task_id,
            "predecessor_task_ids": [context.parent_task_id],
            "bot_id": "estoque-desktop-v1",
            "trigger_bot": context.trigger_bot,
            "timestamp": self.now().astimezone(UTC).isoformat(),
            "status": status,
            "origem_dados": ["desktop"] if records else ["fallback"],
            "modo_degradado": status != "SUCCESS",
            "motivo_fallback": motivo_fallback,
            "attempts": attempts,
            "payload": {
                "records": [record.to_dict() for record in records],
                "source_status": source_status,
                "collected_items": len(records),
                "failed_items": failed_items,
                "latency_ms": latency_ms,
                "evidence_paths": list(evidence_paths),
                "failure_message": failure_message,
            },
            "artifacts": artifacts,
        }

    def _capture_failure_evidence(
        self,
        context: DesktopCollectionContext,
        evidence_paths: list[str],
    ) -> None:
        try:
            evidence = self.driver.capture_evidence(
                self.evidence_dir / f"{context.execution_id}-desktop-failure.png"
            )
        except (DesktopAutomationError, OSError):
            self.logger.warning(
                "Falha ao capturar evidência visual da indisponibilidade desktop",
                extra={"evento": "DESKTOP_EVIDENCE_FAILED"},
            )
        else:
            evidence_paths.append(str(evidence))

    def _capture_attempt_evidence(
        self,
        context: DesktopCollectionContext,
        attempt: int,
        evidence_paths: list[str],
    ) -> None:
        try:
            evidence = self.driver.capture_evidence(
                self.evidence_dir
                / f"{context.execution_id}-desktop-attempt-{attempt}-failed.png"
            )
        except (DesktopAutomationError, OSError):
            return
        evidence_paths.append(str(evidence))

    def _close_driver(self, context: DesktopCollectionContext) -> None:
        try:
            self.driver.close()
        except (DesktopAutomationError, OSError):
            self.logger.warning(
                "Falha controlada ao liberar recursos do driver desktop",
                extra={
                    "evento": "DESKTOP_DRIVER_CLEANUP_FAILED",
                    "correlation_id": context.correlation_id,
                    "current_task_id": context.task_id,
                },
            )

    def _log(self, event: str, context: DesktopCollectionContext, **details: Any) -> None:
        self.logger.info(
            event,
            extra={
                "evento": event,
                "correlation_id": context.correlation_id,
                "root_task_id": context.root_task_id,
                "parent_task_id": context.parent_task_id,
                "current_task_id": context.task_id,
                **details,
            },
        )

    def _latency_ms(self, started: float) -> int:
        return max(0, round((self.clock() - started) * 1000))

    @staticmethod
    def _safe_error(error: Exception) -> str:
        message = str(error).strip()
        return message[:200] if message else type(error).__name__

    @staticmethod
    def _checksum(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
