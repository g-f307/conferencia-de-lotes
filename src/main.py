"""Ciclo principal da automacao."""

from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path
from typing import Any, Iterable, Protocol

from src.bot import LotePerformer, PerformerResult
from src.config import Settings
from src.dispatcher import dispatch_csv
from src.logging_config import configure_logging
from src.maestro_client import MaestroClient
from src.models import ExecutionResult
from src.vault_client import BotCityVaultProvider, VaultClient
from src.web_automation import run_web_automation


class AlertGateway(Protocol):
    """Contrato minimo para emitir alerta de erro no Maestro."""

    def send_error_alert(self, message: str) -> None: ...


class SummaryGateway(AlertGateway, Protocol):
    """Operacoes usadas pelo ciclo principal no Maestro/DataPool."""

    def has_next(self) -> bool: ...

    def next(self) -> dict[str, object]: ...

    def mark_done(self, item: dict[str, object], result: dict[str, str]) -> None: ...

    def mark_business_error(self, item: dict[str, object], error: str) -> None: ...

    def mark_system_error(self, item: dict[str, object], error: str) -> None: ...

    def mark_human_review(self, item: dict[str, object], review: Any) -> None: ...

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
) -> ExecutionResult:
    """Executa o ciclo principal: valida ambiente, consome DataPool e reporta."""
    current_settings = settings or Settings.from_env()
    current_logger = logger or configure_logging(current_settings.log_file)
    result = ExecutionResult()

    try:
        current_settings.validate()
    except ValueError as exc:
        current_logger.error("Configuracao invalida: %s", exc)
        return result.fail(str(exc))

    if not current_settings.input_dir.is_dir():
        message = f"Pasta de entrada inexistente: {current_settings.input_dir}"
        current_logger.error(message)
        gateway = resolve_alert_gateway(current_settings, alert_gateway, maestro_client)
        if gateway is not None:
            try:
                gateway.send_error_alert(message)
            except Exception:
                current_logger.exception("Nao foi possivel emitir o alerta no Maestro")
        return result.fail(message)

    client = maestro_client or MaestroClient(current_settings)
    current_vault_client = vault_client or build_vault_client(current_settings, client)

    try:
        client.send_start_alert()
        current_vault_client.get_erp_credential()
        current_logger.info(
            "Vault validado para a credencial %s", current_settings.vault_label
        )
        if current_settings.web_automation_enabled:
            web_result = run_web_automation(
                current_settings.web_test_url,
                current_settings.base_dir,
                current_settings.web_artifact_dir,
            )
            current_logger.info(
                "Automacao web executada em %s; evidencia salva em %s",
                web_result.url,
                web_result.evidence_path,
            )
        published = dispatch_csv(current_settings.input_csv, client, logger=current_logger)
        current_logger.info("Dispatcher publicou %s itens do CSV configurado", published)
        current_logger.info("Estrutura inicial validada; iniciando consumo do DataPool")
        performer = LotePerformer(
            client,
            reference_lotes or current_settings.reference_lotes,
            current_vault_client,
            processing_delay_seconds=current_settings.processing_delay_seconds,
        )
        result = execution_result_from_performer(performer.run())
        client.post_summary_artifact(result.to_dict(), report_dir=current_settings.report_dir)
        finish_maestro_task(client, result, current_logger)
        current_logger.info(
            "Execucao finalizada com status %s: %s itens, %s sucesso, %s falhas, %s revisoes",
            result.status,
            result.total_items,
            result.processed_items,
            result.failed_items,
            result.ambiguous_items,
        )
        current_logger.info("Automacao encerrada com sucesso operacional")
        return result
    except Exception as exc:
        current_logger.exception("Falha fatal no ciclo principal")
        failed_result = result.fail(str(exc))
        finish_maestro_task(client, failed_result, current_logger)
        return failed_result


def main() -> int:
    """Converte o resultado padronizado em codigo de saida do processo."""
    result = run()
    return 0 if result.status in {"SUCCESS", "PARTIALLY_COMPLETED"} else 1
