"""Encadeamento rastreável dos três bots da conferência de lotes."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Protocol

from src.config import Settings
from src.dispatcher import dispatch_csv
from src.logging_config import LOGGER_NAME, configure_logging
from src.maestro_client import MaestroClient, MaestroTask
from src.wait_for_predecessor import wait_for_predecessor

LOGGER = logging.getLogger(LOGGER_NAME)


class BotStage(str, Enum):
    DISPATCHER = "dispatcher"
    CONFERENCE = "conferencia"
    REPORT = "relatorio"


BOT_LABELS = {
    BotStage.DISPATCHER: "rebecca-dispatcher-v1",
    BotStage.CONFERENCE: "gabriel-conferencia-v1",
    BotStage.REPORT: "marcelo-relatorio-v1",
}
NEXT_STAGE = {
    BotStage.DISPATCHER: BotStage.CONFERENCE,
    BotStage.CONFERENCE: BotStage.REPORT,
}
TERMINAL_SUCCESS_STATUSES = frozenset({"SUCCESS", "PARTIALLY_COMPLETED"})


class OrchestrationGateway(Protocol):
    @property
    def current_task_id(self) -> str: ...

    def create_task(
        self,
        activity_label: str,
        parameters: dict[str, object],
        *,
        priority: int | None = None,
        predecessor_task_ids: Sequence[str] = (),
        timeout_seconds: float | None = None,
    ) -> MaestroTask: ...

    def get_task(self, task_id: str) -> MaestroTask: ...

    def finish_task(
        self,
        status: str,
        message: str,
        total_items: int,
        processed_items: int,
        failed_items: int,
    ) -> None: ...


@dataclass(frozen=True)
class StageResult:
    status: str
    message: str
    payload: dict[str, object] = field(default_factory=dict)
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0

    def __post_init__(self) -> None:
        normalized_status = str(self.status).strip().upper()
        if normalized_status not in {*TERMINAL_SUCCESS_STATUSES, "FAILED"}:
            raise ValueError(f"Status de etapa inválido: {self.status}")
        if any(
            value < 0
            for value in (self.total_items, self.processed_items, self.failed_items)
        ):
            raise ValueError("Contadores da etapa não podem ser negativos")
        json.dumps(self.payload, ensure_ascii=False)
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "message", _required_text(self.message, "message"))

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "payload": self.payload,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "failed_items": self.failed_items,
        }


@dataclass(frozen=True)
class OrchestrationContext:
    stage: BotStage
    current_task_id: str
    correlation_id: str
    root_task_id: str
    parent_task_id: str | None
    trigger_bot: str
    previous_result: dict[str, object]

    @classmethod
    def from_parameters(
        cls,
        stage: BotStage,
        current_task_id: str,
        parameters: Mapping[str, object],
        *,
        correlation_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> OrchestrationContext:
        task_id = _required_text(current_task_id, "current_task_id")
        if stage is BotStage.DISPATCHER:
            correlation_id = str(parameters.get("correlation_id") or "").strip()
            return cls(
                stage=stage,
                current_task_id=task_id,
                correlation_id=correlation_id
                or _required_text(correlation_factory(), "correlation_id"),
                root_task_id=_required_text(
                    parameters.get("root_task_id") or task_id,
                    "root_task_id",
                ),
                parent_task_id=None,
                trigger_bot=_required_text(
                    parameters.get("trigger_bot") or "maestro",
                    "trigger_bot",
                ),
                previous_result={},
            )

        previous_result = parameters.get("previous_result")
        if not isinstance(previous_result, Mapping):
            raise TypeError("previous_result deve ser um objeto para bots dependentes")
        return cls(
            stage=stage,
            current_task_id=task_id,
            correlation_id=_parameter_text(parameters, "correlation_id"),
            root_task_id=_parameter_text(parameters, "root_task_id"),
            parent_task_id=_parameter_text(parameters, "parent_task_id"),
            trigger_bot=_parameter_text(parameters, "trigger_bot"),
            previous_result=dict(previous_result),
        )

    def child_parameters(self, result: StageResult) -> dict[str, object]:
        return {
            "correlation_id": self.correlation_id,
            "root_task_id": self.root_task_id,
            "parent_task_id": self.current_task_id,
            "trigger_bot": BOT_LABELS[self.stage],
            "previous_result": result.to_dict(),
        }


@dataclass(frozen=True)
class OrchestrationOutcome:
    context: OrchestrationContext | None
    result: StageResult
    next_task_id: str | None = None


StageHandler = Callable[[OrchestrationContext], StageResult]


def resolve_stage(bot_id: str) -> BotStage:
    normalized = str(bot_id).strip()
    for stage, label in BOT_LABELS.items():
        if normalized == label:
            return stage
    expected = ", ".join(BOT_LABELS.values())
    raise ValueError(f"BOT_ID não identifica um estágio: esperado {expected}")


def run_orchestrated_stage(
    stage: BotStage,
    gateway: OrchestrationGateway,
    handler: StageHandler,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    logger: logging.Logger = LOGGER,
    wait_fn: Callable[..., MaestroTask] = wait_for_predecessor,
    correlation_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> OrchestrationOutcome:
    """Executa uma etapa, agenda a próxima e sempre produz estado terminal."""
    context: OrchestrationContext | None = None
    try:
        current_task = gateway.get_task(gateway.current_task_id)
        context = OrchestrationContext.from_parameters(
            stage,
            gateway.current_task_id,
            current_task.parameters,
            correlation_factory=correlation_factory,
        )
        _log_stage(logger, context, "INICIO_BOT", "STARTED")

        if context.parent_task_id is not None:
            _log_stage(logger, context, "AGUARDANDO_PREDECESSOR", "WAITING")
            wait_fn(
                gateway,
                context.parent_task_id,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )

        result = handler(context)
        if result.status == "FAILED":
            raise RuntimeError(result.message or "Etapa retornou falha")

        next_task_id = None
        next_stage = NEXT_STAGE.get(stage)
        if next_stage is not None:
            next_task = gateway.create_task(
                BOT_LABELS[next_stage],
                context.child_parameters(result),
            )
            next_task_id = next_task.task_id
            _log_stage(
                logger,
                context,
                "PROXIMA_TASK_CRIADA",
                "SUCCESS",
                next_task_id=next_task_id,
            )

        gateway.finish_task(
            result.status,
            result.message,
            result.total_items,
            result.processed_items,
            result.failed_items,
        )
        _log_stage(logger, context, "FIM_BOT", result.status)
        return OrchestrationOutcome(context, result, next_task_id)
    except Exception as exc:
        failed = StageResult(status="FAILED", message=_failure_message(exc))
        try:
            gateway.finish_task("FAILED", failed.message, 0, 0, 1)
        except Exception:
            logger.exception("Falha ao finalizar task orquestrada no Maestro")
        if context is not None:
            _log_stage(logger, context, "FIM_BOT", "FAILED", error=exc)
        else:
            logger.exception(
                "Falha antes da criação do contexto de orquestração",
                extra={
                    "evento": "FIM_BOT",
                    "formulario": "Orchestrator",
                    "status": "FAILED",
                    "usuario": "sistema",
                },
            )
        return OrchestrationOutcome(context, failed)


def _log_stage(
    logger: logging.Logger,
    context: OrchestrationContext,
    event: str,
    status: str,
    *,
    next_task_id: str | None = None,
    error: Exception | None = None,
) -> None:
    message = f"{BOT_LABELS[context.stage]}: {event.lower()}"
    extra = {
        "evento": event,
        "formulario": "Orchestrator",
        "status": status,
        "usuario": "sistema",
        "correlation_id": context.correlation_id,
        "root_task_id": context.root_task_id,
        "parent_task_id": context.parent_task_id,
        "current_task_id": context.current_task_id,
        "trigger_bot": context.trigger_bot,
        "orchestration_stage": context.stage.value,
        "next_task_id": next_task_id,
    }
    if error is None:
        logger.info(message, extra=extra)
    else:
        logger.error(message, extra=extra, exc_info=error)


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} deve ser informado")
    return normalized


def _parameter_text(parameters: Mapping[str, object], field_name: str) -> str:
    return _required_text(parameters.get(field_name), field_name)


def _failure_message(error: Exception) -> str:
    message = str(error).strip()
    return message or f"{type(error).__name__} sem mensagem"


def run_default_orchestration(
    settings: Settings | None = None,
    maestro_client: MaestroClient | None = None,
    logger: logging.Logger | None = None,
) -> OrchestrationOutcome:
    """Executa o estágio identificado pela atividade da task atual."""
    current_settings = settings or Settings.from_env()
    current_logger = logger or configure_logging(
        current_settings.log_file,
        current_settings,
    )
    client = maestro_client
    try:
        current_settings.validate()
        timeout, poll_interval = _resolve_timeouts(current_settings)
        client = client or MaestroClient(current_settings)
        current_task = client.get_task(client.current_task_id)
        stage_label = current_task.activity_label or current_settings.bot_id
        stage = resolve_stage(stage_label)
        stage_settings = replace(
            current_settings,
            bot_id=BOT_LABELS[stage],
            execution_id=client.current_task_id,
        )
        if logger is None:
            current_logger = configure_logging(
                stage_settings.log_file,
                stage_settings,
            )
    except Exception as exc:  # noqa: BLE001 - toda falha deve finalizar a task
        return _finish_initialization_failure(client, current_logger, exc)

    handlers = {
        BotStage.DISPATCHER: lambda context: _run_dispatcher_stage(
            context,
            stage_settings,
            client,
            current_logger,
        ),
        BotStage.CONFERENCE: lambda context: _run_conference_stage(
            context,
            stage_settings,
            client,
            current_logger,
        ),
        BotStage.REPORT: lambda context: _run_report_stage(
            context,
            stage_settings,
            client,
            current_logger,
        ),
    }
    return run_orchestrated_stage(
        stage,
        client,
        handlers[stage],
        timeout_seconds=timeout,
        poll_interval_seconds=poll_interval,
        logger=current_logger,
    )


def _finish_initialization_failure(
    client: MaestroClient | None,
    logger: logging.Logger,
    error: Exception,
) -> OrchestrationOutcome:
    failed = StageResult(status="FAILED", message=_failure_message(error))
    current_task_id: str | None = None
    if client is not None:
        try:
            current_task_id = client.current_task_id
            client.finish_task("FAILED", failed.message, 0, 0, 1)
        except Exception:
            logger.exception("Falha ao finalizar task durante inicialização")
    logger.error(
        "Falha ao inicializar etapa orquestrada: %s",
        failed.message,
        extra={
            "evento": "FIM_BOT",
            "formulario": "Orchestrator",
            "status": "FAILED",
            "usuario": "sistema",
            "current_task_id": current_task_id,
        },
        exc_info=error,
    )
    return OrchestrationOutcome(None, failed)


def _run_dispatcher_stage(
    context: OrchestrationContext,
    settings: Settings,
    client: MaestroClient,
    logger: logging.Logger,
) -> StageResult:
    if not settings.input_dir.is_dir():
        raise FileNotFoundError(f"Pasta de entrada inexistente: {settings.input_dir}")
    published = dispatch_csv(settings.input_csv, client, logger=logger)
    return StageResult(
        status="SUCCESS",
        message=f"Dispatcher publicou {published} itens",
        payload={
            "published_items": published,
            "datapool_label": settings.datapool_label,
            "correlation_id": context.correlation_id,
        },
        total_items=published,
        processed_items=published,
    )


def _run_conference_stage(
    context: OrchestrationContext,
    settings: Settings,
    client: MaestroClient,
    logger: logging.Logger,
) -> StageResult:
    from src.main import run

    execution = run(
        settings=settings,
        maestro_client=client,
        logger=logger,
        dispatch_items=False,
        publish_results=False,
        finalize_task=False,
    )
    return StageResult(
        status=execution.status,
        message=execution.message or "Conferência concluída",
        payload={"execution_result": execution.to_dict()},
        total_items=execution.total_items,
        processed_items=execution.processed_items,
        failed_items=execution.failed_items + execution.ambiguous_items,
    )


def _run_report_stage(
    context: OrchestrationContext,
    settings: Settings,
    client: MaestroClient,
    logger: logging.Logger,
) -> StageResult:
    stage_payload = context.previous_result.get("payload")
    if not isinstance(stage_payload, Mapping):
        raise TypeError("Resultado anterior não contém payload de conferência")
    summary = stage_payload.get("execution_result")
    if not isinstance(summary, Mapping):
        raise TypeError("Resultado anterior não contém execution_result")
    summary_dict = dict(summary)

    summary_path = client.post_summary_artifact(
        summary_dict,
        report_dir=settings.report_dir,
    )
    report_path = client.post_evidence_report(
        summary_dict,
        {
            "bot_id": settings.bot_id,
            "execution_id": settings.execution_id,
            "correlation_id": context.correlation_id,
            "root_task_id": context.root_task_id,
            "parent_task_id": context.parent_task_id,
            "trigger_bot": context.trigger_bot,
            "datapool_label": settings.datapool_label,
            "vault_label": settings.vault_label,
            "web_enabled": settings.web_automation_enabled,
        },
        report_dir=settings.report_dir,
    )
    client.send_info_alert(
        f"Cadeia {context.correlation_id} concluída; relatório publicado"
    )
    logger.info(
        "Resultados da cadeia publicados: %s e %s",
        summary_path,
        report_path,
        extra={
            "evento": "PUBLICACAO_RESULTADOS",
            "formulario": "Orchestrator",
            "status": "SUCCESS",
            "usuario": "sistema",
            "correlation_id": context.correlation_id,
            "root_task_id": context.root_task_id,
            "parent_task_id": context.parent_task_id,
            "current_task_id": context.current_task_id,
            "trigger_bot": context.trigger_bot,
            "orchestration_stage": context.stage.value,
        },
    )

    total_items = _non_negative_int(summary_dict.get("total_items"), "total_items")
    processed_items = _non_negative_int(
        summary_dict.get("processed_items"),
        "processed_items",
    )
    failed_items = _non_negative_int(
        summary_dict.get("failed_items"),
        "failed_items",
    ) + _non_negative_int(
        summary_dict.get("ambiguous_items"),
        "ambiguous_items",
    )
    return StageResult(
        status="SUCCESS",
        message="Relatórios publicados e cadeia notificada",
        payload={
            "summary_artifact": summary_path.name,
            "evidence_report_artifact": report_path.name,
            "correlation_id": context.correlation_id,
        },
        total_items=total_items,
        processed_items=processed_items,
        failed_items=failed_items,
    )


def _resolve_timeouts(settings: Settings) -> tuple[float, float]:
    timeout = settings.orchestration_timeout_seconds
    poll_interval = settings.orchestration_poll_interval_seconds
    if timeout is None or timeout <= 0:
        raise ValueError("ORCHESTRATION_TIMEOUT_SECONDS deve ser maior que zero")
    if poll_interval is None or poll_interval <= 0:
        raise ValueError(
            "ORCHESTRATION_POLL_INTERVAL_SECONDS deve ser maior que zero"
        )
    return timeout, poll_interval


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} deve ser um inteiro não negativo")
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve ser um inteiro não negativo") from exc
    if converted < 0:
        raise ValueError(f"{field_name} deve ser um inteiro não negativo")
    return converted


def main(settings: Settings | None = None) -> int:
    outcome = run_default_orchestration(settings=settings)
    return 0 if outcome.result.status in TERMINAL_SUCCESS_STATUSES else 1
