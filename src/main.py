"""Ciclo principal da automacao."""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from src.bot import LotePerformer, PerformerResult
from src.classificador_divergencia import ClassificadorDivergencia
from src.config import Settings
from src.dead_letter import DeadLetterWriter
from src.dispatcher import dispatch_csv
from src.item_processor import DivergenceClassifier, ItemProcessor
from src.logging_config import configure_logging
from src.maestro_client import MaestroClient
from src.ml_audit import MLDecisionRecorder
from src.models import ExecutionResult
from src.reference_base import (
    ReferenceBaseService,
    StaticReferenceBaseGateway,
)
from src.retry_policy import LinearRetryPolicy
from src.vault_client import BotCityVaultProvider, VaultClient
from src.web_automation import PlaywrightWebSession, describe_playwright_environment


class AlertGateway(Protocol):
    """Contrato minimo para emitir alerta de erro no Maestro."""

    def send_error_alert(self, message: str) -> None: ...


class SummaryGateway(AlertGateway, Protocol):
    """Operacoes usadas pelo ciclo principal no Maestro/DataPool."""

    def has_next(self) -> bool: ...

    def next(self) -> dict[str, object]: ...

    def mark_done(self, item: dict[str, object], result: dict[str, str]) -> None: ...

    def mark_business_error(
        self,
        item: dict[str, object],
        error: str,
        result: dict[str, str],
    ) -> None: ...

    def mark_system_error(
        self,
        item: dict[str, object],
        error: str,
        result: dict[str, str],
    ) -> None: ...

    def mark_human_review(
        self,
        item: dict[str, object],
        review: Any,
        result: dict[str, str],
    ) -> None: ...

    def mark_ml_offline_review(
        self,
        item: dict[str, object],
        review: Any,
        result: dict[str, str],
    ) -> None: ...

    def send_start_alert(self) -> None: ...

    def finish_task(
        self,
        status: str,
        message: str,
        total_items: int,
        processed_items: int,
        failed_items: int,
    ) -> None: ...

    def post_summary_artifact(
        self,
        summary: dict[str, Any],
        report_dir: Path | None = None,
        artifact_name: str = "resumo_execucao.json",
    ) -> Path: ...

    def post_evidence_report(
        self,
        summary: dict[str, Any],
        metadata: dict[str, Any],
        report_dir: Path | None = None,
        evidence_path: Path | None = None,
        artifact_name: str = "relatorio_evidencias.pdf",
    ) -> Path: ...


class MissingVaultProvider:
    """Falha explicitamente quando ha item a processar sem Vault configurado."""

    def get_credential(self, label: str) -> dict[str, str]:
        raise RuntimeError(
            f"VaultClient nao configurado para recuperar a credencial {label}"
        )


class LocalVaultProvider:
    """Credencial efemera para execucao local sem Maestro Vault."""

    def get_credential(self, label: str) -> dict[str, str]:
        return {
            "username": "local.erp",
            "password": secrets.token_urlsafe(16),
        }


def save_execution_report(result: ExecutionResult, report_dir: Path) -> Path:
    """Persiste o resumo local que depois sera publicado como artefato."""
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "resumo_execucao.json"
    report_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report_path


def execution_result_from_performer(result: PerformerResult) -> ExecutionResult:
    """Converte o resultado do Performer no resumo padronizado do bot."""
    execution = ExecutionResult(
        total_items=result.total,
        processed_items=result.success,
        failed_items=result.business_errors + result.system_errors,
        ambiguous_items=len(result.human_reviews),
        approved_items=result.approved,
        rejected_items=result.rejected,
        divergence_items=result.divergences,
        technical_errors=result.system_errors,
        evidences=list(result.evidences),
        ml_decisions=[decision.to_dict() for decision in result.ml_decisions],
    )
    execution.message = "Processamento concluido"
    return execution.complete()


def build_vault_client(settings: Settings, client: SummaryGateway) -> VaultClient:
    """Monta o Vault real quando o Maestro SDK estiver disponivel."""
    gateway = getattr(client, "gateway", None)
    sdk = getattr(gateway, "sdk", None)
    if settings.vault_enabled and sdk is not None:
        return VaultClient(BotCityVaultProvider(sdk), settings.vault_label)
    if not settings.vault_enabled:
        return VaultClient(LocalVaultProvider(), settings.vault_label)
    return VaultClient(MissingVaultProvider(), settings.vault_label)


def resolve_alert_gateway(
    settings: Settings,
    alert_gateway: AlertGateway | None,
    maestro_client: SummaryGateway | None,
) -> AlertGateway | None:
    """Escolhe um gateway para fail-fast, criando Maestro real se necessario."""
    if alert_gateway is not None:
        return alert_gateway
    if maestro_client is not None:
        return maestro_client
    if settings.maestro_enabled:
        return MaestroClient(settings)
    return None


def finish_maestro_task(
    client: SummaryGateway,
    result: ExecutionResult,
    logger: logging.Logger,
) -> None:
    """Finaliza a task no Maestro sem transformar falha de negócio em falha técnica."""
    failed_items = result.failed_items + result.ambiguous_items
    finish_status = "FAILED" if result.status == "FAILED" else "SUCCESS"
    finish_message = (
        f"{result.message or 'Execucao finalizada'} - "
        f"{result.total_items} itens, {result.processed_items} sucesso, "
        f"{failed_items} falhas/revisoes"
    )

    try:
        client.finish_task(
            finish_status,
            finish_message,
            result.total_items,
            result.processed_items,
            failed_items,
        )
    except AttributeError:
        logger.info("Gateway sem suporte a finish_task; finalizacao ignorada")
    except Exception:
        logger.exception("Nao foi possivel finalizar a task no Maestro")


def run(
    settings: Settings | None = None,
    alert_gateway: AlertGateway | None = None,
    maestro_client: SummaryGateway | None = None,
    vault_client: VaultClient | None = None,
    reference_lotes: Iterable[str] | None = None,
    logger: logging.Logger | None = None,
    divergence_classifier: DivergenceClassifier | None = None,
    dispatch_items: bool = True,
    publish_results: bool = True,
    finalize_task: bool = True,
    reference_base_service: ReferenceBaseService | None = None,
) -> ExecutionResult:
    """Executa o ciclo principal: valida ambiente, consome DataPool e reporta."""
    current_settings = settings or Settings.from_env()
    current_logger = logger or configure_logging(
        current_settings.log_file,
        current_settings,
    )
    result = ExecutionResult()

    try:
        current_settings.validate()
    except ValueError as exc:
        current_logger.error(
            "Configuracao invalida: %s",
            exc,
            extra={
                "evento": "VALIDACAO_CONFIGURACAO",
                "formulario": "Inicializacao",
                "status": "FAILED",
                "usuario": "sistema",
            },
        )
        return result.fail(str(exc))

    if not current_settings.input_dir.is_dir():
        message = f"Pasta de entrada inexistente: {current_settings.input_dir}"
        current_logger.error(
            message,
            extra={
                "evento": "VALIDACAO_ENTRADA",
                "formulario": "Inicializacao",
                "status": "FAILED",
                "usuario": "sistema",
            },
        )
        gateway = resolve_alert_gateway(current_settings, alert_gateway, maestro_client)
        if gateway is not None:
            try:
                gateway.send_error_alert(message)
            except Exception:
                current_logger.exception("Nao foi possivel emitir o alerta no Maestro")
        return result.fail(message)

    client = maestro_client or MaestroClient(current_settings)
    current_vault_client = vault_client or build_vault_client(current_settings, client)
    web_session: PlaywrightWebSession | None = None

    try:
        client.send_start_alert()
        erp_credential = current_vault_client.get_erp_credential()
        current_logger.info(
            "Vault validado para a credencial %s",
            current_settings.vault_label,
            extra={
                "evento": "VALIDACAO_VAULT",
                "formulario": "Vault",
                "status": "SUCCESS",
                "usuario": "sistema",
            },
        )
        if current_settings.web_automation_enabled:
            playwright_environment = describe_playwright_environment()
            current_logger.info(
                "Ambiente Playwright: engine=%s, navegador=%s (%s), headless=%s",
                playwright_environment["engine"],
                playwright_environment["browser_path"],
                playwright_environment["browser_version"],
                playwright_environment["headless"],
                extra={
                    "evento": "PLAYWRIGHT_AMBIENTE",
                    "formulario": "Index Lotes",
                    "status": "SUCCESS",
                    "usuario": "sistema",
                },
            )
            web_session = PlaywrightWebSession(
                current_settings.web_test_url,
                current_settings.base_dir,
                current_settings.web_artifact_dir,
                timeout_seconds=current_settings.web_timeout_seconds,
            )
            web_session.start(erp_credential)
            current_logger.info(
                "Sessão Playwright autenticada e pronta para processar itens",
                extra={
                    "evento": "INICIO_PLAYWRIGHT",
                    "formulario": "Index Lotes",
                    "status": "SUCCESS",
                    "usuario": "sistema",
                },
            )
        if dispatch_items:
            published = dispatch_csv(
                current_settings.input_csv,
                client,
                logger=current_logger,
            )
            current_logger.info(
                "Dispatcher publicou %s itens do CSV configurado",
                published,
                extra={
                    "evento": "PUBLICACAO_CSV",
                    "formulario": "Dispatcher",
                    "status": "SUCCESS",
                    "usuario": "sistema",
                },
            )
        current_logger.info(
            "Estrutura inicial validada; iniciando consumo do DataPool",
            extra={
                "evento": "INICIO_PROCESSAMENTO",
                "formulario": "DataPool",
                "status": "STARTED",
                "usuario": "sistema",
            },
        )
        current_reference_lotes = tuple(
            reference_lotes or current_settings.reference_lotes
        )
        current_reference_base = reference_base_service
        if current_reference_base is None:
            assert current_settings.reference_max_attempts is not None
            assert current_settings.reference_retry_base_interval_seconds is not None
            assert current_settings.reference_timeout_seconds is not None
            assert current_settings.dead_letter_path is not None
            retry_policy = LinearRetryPolicy(
                max_attempts=current_settings.reference_max_attempts,
                base_interval_seconds=(
                    current_settings.reference_retry_base_interval_seconds
                ),
                timeout_seconds=current_settings.reference_timeout_seconds,
            )
            dead_letter = DeadLetterWriter(
                current_settings.dead_letter_path,
                execution_id=current_settings.execution_id,
                task_id=(
                    current_settings.maestro_task_id
                    or current_settings.execution_id
                ),
            )
            current_reference_base = ReferenceBaseService(
                StaticReferenceBaseGateway(current_reference_lotes),
                retry_policy,
                dead_letter,
                alert_gateway=client,
                logger=current_logger,
            )
        current_divergence_classifier = (
            divergence_classifier
            or ClassificadorDivergencia.from_settings(current_settings)
        )
        item_processor = ItemProcessor(
            current_reference_lotes,
            divergence_classifier=current_divergence_classifier,
            decision_recorder=MLDecisionRecorder(
                current_settings.bot_id,
                current_settings.execution_id,
            ),
            reference_base=current_reference_base,
        )
        performer = LotePerformer(
            client,
            current_reference_lotes,
            current_vault_client,
            processing_delay_seconds=current_settings.processing_delay_seconds,
            web_processor=web_session,
            item_processor=item_processor,
        )
        result = execution_result_from_performer(performer.run())
        if publish_results:
            summary = result.to_dict()
            summary_path = client.post_summary_artifact(
                summary,
                report_dir=current_settings.report_dir,
            )
            report_evidence = (
                current_settings.base_dir / result.evidences[0]
                if result.evidences
                else None
            )
            evidence_report_path = client.post_evidence_report(
                summary,
                {
                    "bot_id": current_settings.bot_id,
                    "execution_id": current_settings.execution_id,
                    "datapool_label": current_settings.datapool_label,
                    "vault_label": current_settings.vault_label,
                    "web_enabled": current_settings.web_automation_enabled,
                },
                report_dir=current_settings.report_dir,
                evidence_path=report_evidence,
            )
            current_logger.info(
                "Resultados gerados: %s e %s",
                summary_path,
                evidence_report_path,
                extra={
                    "evento": "PUBLICACAO_RESULTADOS",
                    "formulario": "Resumo",
                    "status": "SUCCESS",
                    "usuario": "sistema",
                },
            )
        if finalize_task:
            finish_maestro_task(client, result, current_logger)
        current_logger.info(
            "Execucao finalizada com status %s: %s itens, %s sucesso, %s falhas, %s revisoes",
            result.status,
            result.total_items,
            result.processed_items,
            result.failed_items,
            result.ambiguous_items,
            extra={
                "evento": "FIM_PROCESSAMENTO",
                "formulario": "Resumo",
                "status": result.status,
                "usuario": "sistema",
            },
        )
        current_logger.info(
            "Automacao encerrada com sucesso operacional",
            extra={
                "evento": "ENCERRAMENTO",
                "formulario": "Sistema",
                "status": "SUCCESS",
                "usuario": "sistema",
            },
        )
        return result
    except Exception as exc:
        current_logger.exception(
            "Falha fatal no ciclo principal",
            extra={
                "evento": "ERRO_FATAL",
                "formulario": "Sistema",
                "status": "FAILED",
                "usuario": "sistema",
            },
        )
        failed_result = result.fail(str(exc))
        if finalize_task:
            finish_maestro_task(client, failed_result, current_logger)
        return failed_result
    finally:
        if web_session is not None:
            web_session.close()
            current_logger.info(
                "Sessão Playwright encerrada",
                extra={
                    "evento": "FIM_PLAYWRIGHT",
                    "formulario": "Index Lotes",
                    "status": "SUCCESS",
                    "usuario": "sistema",
                },
            )


def main(settings: Settings | None = None) -> int:
    """Converte o resultado padronizado em codigo de saida do processo."""
    result = run(settings=settings)
    return 0 if result.status in {"SUCCESS", "PARTIALLY_COMPLETED"} else 1
