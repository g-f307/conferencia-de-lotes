from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

from src.validation import HumanReviewRequired, HumanReviewStatus, ValidationError, validate_lote
from src.vault_client import ErpCredential, VaultClient


LOGGER = logging.getLogger(__name__)


class QueueAdapter(Protocol):
    def has_next(self) -> bool:
        raise NotImplementedError

    def next(self) -> dict[str, object] | None:
        raise NotImplementedError

    def mark_done(self, item: dict[str, object], result: dict[str, str]) -> None:
        raise NotImplementedError

    def mark_business_error(self, item: dict[str, object], error: str) -> None:
        raise NotImplementedError

    def mark_system_error(self, item: dict[str, object], error: str) -> None:
        raise NotImplementedError

    def mark_human_review(self, item: dict[str, object], review: HumanReviewRequired) -> None:
        raise NotImplementedError


@dataclass
class PerformerResult:
    total: int = 0
    success: int = 0
    business_errors: int = 0
    system_errors: int = 0
    human_reviews: list[HumanReviewRequired] = field(default_factory=list)


class QueueItemFetchError(RuntimeError):
    """Falha tecnica antes de existir item do DataPool para finalizar."""


class LotePerformer:
    def __init__(
        self,
        queue: QueueAdapter,
        reference_lotes: Iterable[str],
        vault_client: VaultClient,
        processing_delay_seconds: float = 0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.queue = queue
        self.reference_lotes = tuple(reference_lotes)
        self.vault_client = vault_client
        self.processing_delay_seconds = processing_delay_seconds
        self.sleep_fn = sleep_fn

    def run(self) -> PerformerResult:
        result = PerformerResult()
        credential_logged = False
        while self.queue.has_next():
            try:
                item = self.queue.next()
            except Exception as exc:
                LOGGER.exception(
                    "Falha tecnica ao obter item da fila",
                    extra={
                        "evento": "LEITURA_DATAPOOL",
                        "formulario": "FilaAuditoriaLotes",
                        "status": "FAILED",
                        "usuario": "sistema",
                    },
                )
                raise QueueItemFetchError("Falha tecnica ao obter item da fila") from exc

            if item is None:
                LOGGER.info(
                    "DataPool retornou item vazio; encerrando consumo",
                    extra={
                        "evento": "FIM_DATAPOOL",
                        "formulario": "FilaAuditoriaLotes",
                        "status": "SUCCESS",
                        "usuario": "sistema",
                    },
                )
                break

            result.total += 1
            try:
                if not credential_logged:
                    credential = self.vault_client.get_erp_credential()
                    self._log_erp_user(credential)
                    credential_logged = True
                validated = validate_lote(item, self.reference_lotes)
                if self.processing_delay_seconds > 0:
                    self.sleep_fn(self.processing_delay_seconds)
                self.queue.mark_done(item, validated)
                result.success += 1
            except HumanReviewStatus as exc:
                review = HumanReviewRequired(
                    lote_id=str(item.get("lote_id") or "").strip(),
                    status_original=exc.status,
                )
                self.queue.mark_human_review(item, review)
                result.human_reviews.append(review)
            except ValidationError as exc:
                self.queue.mark_business_error(item, str(exc))
                result.business_errors += 1
            except Exception as exc:
                LOGGER.exception(
                    "Falha tecnica ao processar item da fila",
                    extra={
                        "evento": "PROCESSAMENTO_LOTE",
                        "formulario": "Auditoria de Lotes",
                        "status": "FAILED",
                        "usuario": "sistema",
                    },
                )
                self.queue.mark_system_error(item, str(exc))
                result.system_errors += 1

        return result

    def _log_erp_user(self, credential: ErpCredential) -> None:
        LOGGER.info(
            "ERP autenticado com usuario %s",
            credential.username,
            extra={
                "evento": "AUTENTICACAO_ERP",
                "formulario": "Login ERP",
                "status": "SUCCESS",
                "usuario": credential.username,
            },
        )
