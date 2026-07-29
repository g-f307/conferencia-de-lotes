from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from src.logging_config import LOGGER_NAME
from src.validation import (
    HumanReviewRequired,
    HumanReviewStatus,
    ValidationError,
    validate_lote,
)
from src.vault_client import ErpCredential, VaultClient


LOGGER = logging.getLogger(LOGGER_NAME)
DATAPOOL_LOG_LABEL = "FilaAuditoriaLotes2"
OUTPUT_RESULTADO = "resultado_validacao"
OUTPUT_EVIDENCIA = "evidencia"
OUTPUT_MENSAGEM = "mensagem_resultado"


class QueueAdapter(Protocol):
    def has_next(self) -> bool: ...

    def next(self) -> Mapping[str, object] | None: ...

    def mark_done(
        self,
        item: Mapping[str, object],
        result: dict[str, str],
    ) -> None: ...

    def mark_business_error(
        self,
        item: Mapping[str, object],
        error: str,
        result: dict[str, str],
    ) -> None: ...

    def mark_system_error(
        self,
        item: Mapping[str, object],
        error: str,
        result: dict[str, str],
    ) -> None: ...

    def mark_human_review(
        self,
        item: Mapping[str, object],
        review: HumanReviewRequired,
        result: dict[str, str],
    ) -> None: ...


class WebItemProcessor(Protocol):
    base_dir: Path

    def process_item(
        self,
        item: Mapping[str, object],
        resultado_validacao: str,
        mensagem_resultado: str,
    ) -> Any: ...

    def capture_error(self, item: Mapping[str, object]) -> Path | None: ...


@dataclass(frozen=True)
class ItemClassification:
    resultado: str
    mensagem: str
    validated: dict[str, str] = field(default_factory=dict)
    review: HumanReviewRequired | None = None


@dataclass
class PerformerResult:
    total: int = 0
    success: int = 0
    business_errors: int = 0
    system_errors: int = 0
    human_reviews: list[HumanReviewRequired] = field(default_factory=list)
    evidences: list[str] = field(default_factory=list)

    @property
    def approved(self) -> int:
        return self.success

    @property
    def divergences(self) -> int:
        return self.business_errors


class QueueItemFetchError(RuntimeError):
    """Falha técnica antes de existir item do DataPool para finalizar."""


class LotePerformer:
    def __init__(
        self,
        queue: QueueAdapter,
        reference_lotes: Iterable[str],
        vault_client: VaultClient,
        processing_delay_seconds: float = 0,
        sleep_fn: Callable[[float], None] = time.sleep,
        web_processor: WebItemProcessor | None = None,
    ) -> None:
        self.queue = queue
        self.reference_lotes = tuple(reference_lotes)
        self.vault_client = vault_client
        self.processing_delay_seconds = processing_delay_seconds
        self.sleep_fn = sleep_fn
        self.web_processor = web_processor

    def run(self) -> PerformerResult:
        result = PerformerResult()
        credential_logged = False

        while self.queue.has_next():
            item = self._next_item()
            if item is None:
                break

            result.total += 1
            lote_id = str(item.get("lote_id") or "").strip() or "lote-sem-id"
            LOGGER.info(
                "Iniciando processamento do item %s",
                lote_id,
                extra=self._log_context("INICIO_ITEM", "STARTED"),
            )

            if not credential_logged:
                credential = self.vault_client.get_erp_credential()
                self._log_erp_user(credential)
                credential_logged = True

            classification = self._classify(item)
            try:
                evidence, message = self._process_web(item, classification)
            except Exception as exc:
                self._handle_web_failure(item, exc, result)
                continue

            outputs = self._outputs(
                classification.resultado,
                message,
                evidence,
            )
            self._finish_classified_item(item, classification, outputs, result)

            if (
                classification.resultado == "APROVADO"
                and self.processing_delay_seconds > 0
            ):
                self.sleep_fn(self.processing_delay_seconds)

            LOGGER.info(
                "Item %s finalizado como %s; evidencia=%s",
                lote_id,
                classification.resultado,
                outputs[OUTPUT_EVIDENCIA] or "não gerada",
                extra=self._log_context(
                    "RESULTADO_ITEM",
                    classification.resultado,
                ),
            )

        return result

    def _next_item(self) -> Mapping[str, object] | None:
        try:
            item = self.queue.next()
        except Exception as exc:
            LOGGER.exception(
                "Falha técnica ao obter item da fila",
                extra=self._log_context("LEITURA_DATAPOOL", "FAILED"),
            )
            raise QueueItemFetchError("Falha técnica ao obter item da fila") from exc

        if item is None:
            LOGGER.info(
                "DataPool retornou item vazio; encerrando consumo",
                extra=self._log_context("FIM_DATAPOOL", "SUCCESS"),
            )
        return item

    def _classify(self, item: Mapping[str, object]) -> ItemClassification:
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
                resultado="DIVERGENCIA",
                mensagem=f"Lote reprovado: {observation}",
                validated=validated,
            )

        return ItemClassification(
            resultado="APROVADO",
            mensagem="Lote aprovado pelas regras RN01–RN07",
            validated=validated,
        )

    def _process_web(
        self,
        item: Mapping[str, object],
        classification: ItemClassification,
    ) -> tuple[str, str]:
        if self.web_processor is None:
            return "", classification.mensagem

        web_result = self.web_processor.process_item(
            item,
            classification.resultado,
            classification.mensagem,
        )
        relative_path = self._relative_path(web_result.evidence_path)
        LOGGER.info(
            "Evidência gerada para o item: %s",
            relative_path,
            extra=self._log_context("EVIDENCIA_ITEM", "SUCCESS"),
        )
        return relative_path, str(
            getattr(web_result, "mensagem_resultado", "")
            or classification.mensagem
        )

    def _handle_web_failure(
        self,
        item: Mapping[str, object],
        exc: Exception,
        result: PerformerResult,
    ) -> None:
        evidence = ""
        if self.web_processor is not None:
            captured = self.web_processor.capture_error(item)
            if captured is not None:
                evidence = self._relative_path(captured)
                result.evidences.append(evidence)

        message = f"Falha técnica na automação web: {exc}"
        outputs = self._outputs("ERRO", message, evidence)
        LOGGER.exception(
            "Falha técnica ao processar item na página controlada",
            extra=self._log_context("ERRO_WEB_ITEM", "FAILED"),
        )
        self.queue.mark_system_error(item, message, outputs)
        result.system_errors += 1

    def _finish_classified_item(
        self,
        item: Mapping[str, object],
        classification: ItemClassification,
        outputs: dict[str, str],
        result: PerformerResult,
    ) -> None:
        evidence = outputs[OUTPUT_EVIDENCIA]
        if evidence:
            result.evidences.append(evidence)

        if classification.resultado == "APROVADO":
            self.queue.mark_done(
                item,
                {**classification.validated, **outputs},
            )
            result.success += 1
            return

        if classification.resultado == "REVISAO":
            assert classification.review is not None
            self.queue.mark_human_review(
                item,
                classification.review,
                outputs,
            )
            result.human_reviews.append(classification.review)
            return

        self.queue.mark_business_error(item, classification.mensagem, outputs)
        result.business_errors += 1

    @staticmethod
    def _outputs(
        resultado: str,
        mensagem: str,
        evidence: str,
    ) -> dict[str, str]:
        return {
            OUTPUT_RESULTADO: resultado,
            OUTPUT_EVIDENCIA: evidence,
            OUTPUT_MENSAGEM: mensagem,
        }

    def _relative_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(
                self.web_processor.base_dir.resolve()  # type: ignore[union-attr]
            ).as_posix()
        except ValueError:
            return path.name

    def _log_erp_user(self, credential: ErpCredential) -> None:
        LOGGER.info(
            "ERP autenticado com usuário %s",
            credential.username,
            extra={
                **self._log_context("AUTENTICACAO_ERP", "SUCCESS"),
                "usuario": credential.username,
            },
        )

    @staticmethod
    def _log_context(evento: str, status: str) -> dict[str, str]:
        return {
            "evento": evento,
            "formulario": DATAPOOL_LOG_LABEL,
            "status": status,
            "usuario": "sistema",
        }
