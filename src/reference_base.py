"""Consulta resiliente e testável à Base de Referência."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from src.dead_letter import DeadLetterWriter
from src.logging_config import LOGGER_NAME, sanitize_text
from src.retry_policy import LinearRetryPolicy

LOGGER = logging.getLogger(LOGGER_NAME)


class ReferenceInfrastructureError(RuntimeError):
    """Falha transitória de acesso, conexão ou timeout."""


class ReferenceDataError(ValueError):
    """Resposta ou dado incompatível com o contrato da Base de Referência."""


class ReferenceLookupStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    PENDING_REVIEW = "PENDENTE_REVISAO"
    DATA_FAILURE = "DATA_FAILURE"


@dataclass(frozen=True)
class ReferenceLookupResult:
    status: ReferenceLookupStatus
    attempts: int
    reason: str = ""

    @property
    def exists(self) -> bool:
        return self.status is ReferenceLookupStatus.FOUND


class ReferenceBaseGateway(Protocol):
    def contains(self, lote_id: str, *, timeout_seconds: float) -> bool: ...


class OperationalAlertGateway(Protocol):
    def send_error_alert(self, message: str) -> None: ...


class StaticReferenceBaseGateway:
    """Adapta a lista atual de referências ao novo contrato resiliente."""

    def __init__(self, reference_lotes: Iterable[object]) -> None:
        self.reference_lotes = {
            str(lote or "").strip()
            for lote in reference_lotes
            if str(lote or "").strip()
        }

    def contains(self, lote_id: str, *, timeout_seconds: float) -> bool:
        del timeout_seconds
        return lote_id in self.reference_lotes


class ReferenceBaseService:
    """Diferencia indisponibilidade transitória de falha repetida de dados."""

    def __init__(
        self,
        gateway: ReferenceBaseGateway,
        retry_policy: LinearRetryPolicy,
        dead_letter: DeadLetterWriter,
        *,
        alert_gateway: OperationalAlertGateway | None = None,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.gateway = gateway
        self.retry_policy = retry_policy
        self.dead_letter = dead_letter
        self.alert_gateway = alert_gateway
        self.logger = logger

    def lookup(self, item: Mapping[str, object]) -> ReferenceLookupResult:
        lote_id = str(item.get("lote_id") or "").strip()
        infrastructure_errors: list[Exception] = []
        data_errors: list[ReferenceDataError] = []

        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                result = self.gateway.contains(
                    lote_id,
                    timeout_seconds=self.retry_policy.timeout_seconds,
                )
                if not isinstance(result, bool):
                    raise ReferenceDataError(
                        "Base de Referência retornou um resultado não booleano"
                    )
            except ReferenceDataError as exc:
                data_errors.append(exc)
                if attempt < self.retry_policy.max_attempts:
                    continue
            except (ReferenceInfrastructureError, OSError) as exc:
                infrastructure_errors.append(exc)
                if attempt < self.retry_policy.max_attempts:
                    self.retry_policy.wait_before_retry(attempt)
                    continue
            else:
                status = (
                    ReferenceLookupStatus.FOUND
                    if result
                    else ReferenceLookupStatus.NOT_FOUND
                )
                self._log(
                    "CONSULTA_BASE_REFERENCIA",
                    "SUCCESS",
                    lote_id,
                    attempt,
                    "Lote localizado" if result else "Lote não localizado",
                )
                return ReferenceLookupResult(status, attempts=attempt)

        attempts = self.retry_policy.max_attempts
        if infrastructure_errors:
            reason = (
                "Base de Referência indisponível após "
                f"{attempts} tentativa(s): "
                f"{_error_message(infrastructure_errors[-1])}"
            )
            self._request_operational_alert(reason, lote_id)
            self._log(
                "BASE_REFERENCIA_INDISPONIVEL",
                "PENDENTE_REVISAO",
                lote_id,
                attempts,
                reason,
            )
            return ReferenceLookupResult(
                ReferenceLookupStatus.PENDING_REVIEW,
                attempts=attempts,
                reason=reason,
            )

        if data_errors:
            reason = _error_message(data_errors[-1])
            self.dead_letter.write(
                item,
                reason=reason,
                attempts=attempts,
            )
            self._log(
                "DEAD_LETTER_DADOS",
                "FAILED",
                lote_id,
                attempts,
                reason,
            )
            return ReferenceLookupResult(
                ReferenceLookupStatus.DATA_FAILURE,
                attempts=attempts,
                reason=reason,
            )

        raise AssertionError("Consulta da Base de Referência terminou sem resultado")

    def _request_operational_alert(self, reason: str, lote_id: str) -> None:
        if self.alert_gateway is None:
            return
        try:
            self.alert_gateway.send_error_alert(
                f"Base de Referência indisponível; lote {lote_id or 'sem-id'} "
                f"encaminhado para PENDENTE_REVISAO. {reason}"
            )
        except Exception:
            self.logger.exception(
                "Falha ao solicitar alerta operacional da Base de Referência",
                extra={
                    "evento": "ALERTA_BASE_REFERENCIA",
                    "formulario": "Base de Referência",
                    "status": "FAILED",
                    "usuario": "sistema",
                    "lote_id": lote_id,
                },
            )

    def _log(
        self,
        event: str,
        status: str,
        lote_id: str,
        attempts: int,
        message: str,
    ) -> None:
        self.logger.info(
            "%s; tentativas=%s",
            sanitize_text(message),
            attempts,
            extra={
                "evento": event,
                "formulario": "Base de Referência",
                "status": status,
                "usuario": "sistema",
                "lote_id": lote_id,
                "reference_attempts": attempts,
            },
        )


def _error_message(error: Exception) -> str:
    message = str(error).strip()
    return sanitize_text(message or f"{type(error).__name__} sem mensagem")
