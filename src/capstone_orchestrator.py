"""Orchestration of the six Capstone bots as a bounded, traceable DAG."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Protocol

from src.logging_config import LOGGER_NAME
from src.maestro_client import MaestroTask
from src.orchestrator import StageResult
from src.wait_for_predecessor import (
    PredecessorCanceledError,
    PredecessorFailedError,
    PredecessorTimeoutError,
    wait_for_predecessor,
)

LOGGER = logging.getLogger(LOGGER_NAME)


class CapstoneStage(str, Enum):
    DISPATCHER = "dispatcher"
    DESKTOP = "estoque_desktop"
    WEB = "fornecedores_web"
    CONSOLIDATION = "consolidacao"
    ML = "classificador_ml"
    REPORT = "relatorio_alertas"


CAPSTONE_BOT_LABELS = {
    CapstoneStage.DISPATCHER: "dispatcher-v2",
    CapstoneStage.DESKTOP: "estoque-desktop-v1",
    CapstoneStage.WEB: "fornecedores-web-v1",
    CapstoneStage.CONSOLIDATION: "consolidacao-v2",
    CapstoneStage.ML: "classificador-ml-v1",
    CapstoneStage.REPORT: "relatorio-alertas-v2",
}


class CapstoneGateway(Protocol):
    @property
    def current_task_id(self) -> str: ...

    def create_task(
        self,
        activity_label: str,
        parameters: Mapping[str, object],
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
class CapstoneOrchestrationSettings:
    desktop_priority: int = 100
    default_priority: int = 50
    dependency_timeout_seconds: float = 300.0
    poll_interval_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.desktop_priority <= self.default_priority:
            raise ValueError("desktop_priority deve ser maior que default_priority")
        if self.dependency_timeout_seconds <= 0:
            raise ValueError("dependency_timeout_seconds deve ser maior que zero")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds deve ser maior que zero")

    @classmethod
    def from_env(cls) -> CapstoneOrchestrationSettings:
        return cls(
            desktop_priority=int(os.getenv("SMART_OFFICE_DESKTOP_PRIORITY", "100")),
            default_priority=int(os.getenv("SMART_OFFICE_DEFAULT_PRIORITY", "50")),
            dependency_timeout_seconds=float(
                os.getenv("SMART_OFFICE_DEPENDENCY_TIMEOUT_SECONDS", "300")
            ),
            poll_interval_seconds=float(
                os.getenv("SMART_OFFICE_POLL_INTERVAL_SECONDS", "2")
            ),
        )


@dataclass(frozen=True)
class PipelineManifest:
    execution_id: str
    correlation_id: str
    root_task_id: str
    task_ids: Mapping[CapstoneStage, str]
    creation_failures: Mapping[CapstoneStage, str] = field(default_factory=dict)

    def task_id(self, stage: CapstoneStage) -> str | None:
        return self.task_ids.get(stage)


@dataclass(frozen=True)
class DependencyResult:
    task_id: str
    status: str
    message: str

    @property
    def successful(self) -> bool:
        return self.status in {"SUCCESS", "PARTIALLY_COMPLETED"}


@dataclass(frozen=True)
class CapstoneContext:
    stage: CapstoneStage
    current_task_id: str
    execution_id: str
    correlation_id: str
    root_task_id: str
    parent_task_id: str
    predecessor_task_ids: tuple[str, ...]
    dependency_results: tuple[DependencyResult, ...]
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class CapstoneOutcome:
    context: CapstoneContext
    result: StageResult


WaitFunction = Callable[..., MaestroTask]
StageHandler = Callable[[CapstoneContext], StageResult]


class CapstoneOrchestrator:
    """Schedule and execute six bots while preserving the legacy orchestrator."""

    _DEGRADED_STAGES = frozenset(
        {CapstoneStage.CONSOLIDATION, CapstoneStage.REPORT}
    )

    def __init__(
        self,
        gateway: CapstoneGateway,
        *,
        settings: CapstoneOrchestrationSettings | None = None,
        wait_function: WaitFunction = wait_for_predecessor,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.gateway = gateway
        self.settings = settings or CapstoneOrchestrationSettings.from_env()
        self.wait_function = wait_function
        self.logger = logger

    def schedule(
        self,
        *,
        execution_id: str | None = None,
        correlation_id: str | None = None,
    ) -> PipelineManifest:
        root_task_id = self.gateway.current_task_id
        execution = execution_id or str(uuid.uuid4())
        correlation = correlation_id or str(uuid.uuid4())
        task_ids: dict[CapstoneStage, str] = {
            CapstoneStage.DISPATCHER: root_task_id
        }
        failures: dict[CapstoneStage, str] = {}

        desktop = self._create(
            CapstoneStage.DESKTOP,
            (root_task_id,),
            execution,
            correlation,
            root_task_id,
            self.settings.desktop_priority,
            failures,
        )
        web = self._create(
            CapstoneStage.WEB,
            (root_task_id,),
            execution,
            correlation,
            root_task_id,
            self.settings.default_priority,
            failures,
        )
        source_ids = tuple(task.task_id for task in (desktop, web) if task is not None)
        consolidation = self._create(
            CapstoneStage.CONSOLIDATION,
            source_ids,
            execution,
            correlation,
            root_task_id,
            self.settings.default_priority,
            failures,
        )
        ml_predecessors = (consolidation.task_id,) if consolidation else ()
        ml = self._create(
            CapstoneStage.ML,
            ml_predecessors,
            execution,
            correlation,
            root_task_id,
            self.settings.default_priority,
            failures,
        )
        if ml is not None:
            report_predecessors = (ml.task_id,)
        elif consolidation is not None:
            report_predecessors = (consolidation.task_id,)
        else:
            report_predecessors = ()
        report = self._create(
            CapstoneStage.REPORT,
            report_predecessors,
            execution,
            correlation,
            root_task_id,
            self.settings.default_priority,
            failures,
        )

        for stage, task in (
            (CapstoneStage.DESKTOP, desktop),
            (CapstoneStage.WEB, web),
            (CapstoneStage.CONSOLIDATION, consolidation),
            (CapstoneStage.ML, ml),
        ):
            if task is not None:
                task_ids[stage] = task.task_id
        if report is not None:
            task_ids[CapstoneStage.REPORT] = report.task_id

        status = "PARTIALLY_COMPLETED" if failures else "SUCCESS"
        self.gateway.finish_task(
            status,
            "Pipeline Capstone agendado" if not failures else "Pipeline agendado com degradacao",
            5,
            5 - len(failures),
            len(failures),
        )
        self.logger.info(
            "dispatcher concluido execution_id=%s correlation_id=%s root_task_id=%s status=%s",
            execution,
            correlation,
            root_task_id,
            status,
        )
        return PipelineManifest(execution, correlation, root_task_id, task_ids, failures)

    def execute_current(
        self,
        stage: CapstoneStage,
        handler: StageHandler,
    ) -> CapstoneOutcome:
        if stage is CapstoneStage.DISPATCHER:
            raise ValueError("Use schedule() para executar o dispatcher")
        current = self.gateway.get_task(self.gateway.current_task_id)
        parameters = current.parameters
        predecessors = tuple(
            current.predecessor_task_ids
            or tuple(parameters.get("predecessor_task_ids", ()))
        )
        results = tuple(self._wait(task_id) for task_id in predecessors)
        context = CapstoneContext(
            stage=stage,
            current_task_id=current.task_id,
            execution_id=str(parameters.get("execution_id", "")),
            correlation_id=str(parameters.get("correlation_id", "")),
            root_task_id=str(parameters.get("root_task_id", "")),
            parent_task_id=str(parameters.get("parent_task_id", "")),
            predecessor_task_ids=predecessors,
            dependency_results=results,
            parameters=parameters,
        )
        degraded = any(not result.successful for result in results)
        if degraded and stage not in self._DEGRADED_STAGES:
            result = StageResult(
                "FAILED",
                "Etapa bloqueada por dependencia sem sucesso",
                payload={"dependencies": [result.__dict__ for result in results]},
                failed_items=1,
            )
        else:
            result = handler(context)
            if degraded and result.status == "SUCCESS":
                result = replace(
                    result,
                    status="PARTIALLY_COMPLETED",
                    message=f"{result.message} (execucao degradada)",
                )
        self.gateway.finish_task(
            result.status,
            result.message,
            result.total_items,
            result.processed_items,
            result.failed_items,
        )
        self.logger.info(
            "task concluida stage=%s task_id=%s execution_id=%s correlation_id=%s status=%s",
            stage.value,
            current.task_id,
            context.execution_id,
            context.correlation_id,
            result.status,
        )
        return CapstoneOutcome(context, result)

    def _create(
        self,
        stage: CapstoneStage,
        predecessors: tuple[str, ...],
        execution_id: str,
        correlation_id: str,
        root_task_id: str,
        priority: int,
        failures: dict[CapstoneStage, str],
    ) -> MaestroTask | None:
        parameters: dict[str, object] = {
            "schema_version": "1.0",
            "stage": stage.value,
            "execution_id": execution_id,
            "correlation_id": correlation_id,
            "root_task_id": root_task_id,
            "parent_task_id": root_task_id,
            "predecessor_task_ids": list(predecessors),
            "upstream_creation_failures": {
                failed_stage.value: reason for failed_stage, reason in failures.items()
            },
        }
        try:
            task = self.gateway.create_task(
                CAPSTONE_BOT_LABELS[stage],
                parameters,
                priority=priority,
                predecessor_task_ids=predecessors,
                timeout_seconds=self.settings.dependency_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 -- gateway is an external boundary
            failures[stage] = str(exc)
            self.logger.error(
                "falha ao criar task stage=%s execution_id=%s correlation_id=%s error=%s",
                stage.value,
                execution_id,
                correlation_id,
                exc,
            )
            return None
        self.logger.info(
            "task criada stage=%s task_id=%s execution_id=%s correlation_id=%s parent_task_id=%s predecessors=%s priority=%s timeout=%s",
            stage.value,
            task.task_id,
            execution_id,
            correlation_id,
            root_task_id,
            predecessors,
            priority,
            self.settings.dependency_timeout_seconds,
        )
        return task

    def _wait(self, task_id: str) -> DependencyResult:
        self.logger.info("aguardando predecessor task_id=%s", task_id)
        try:
            task = self.wait_function(
                self.gateway,
                task_id,
                timeout_seconds=self.settings.dependency_timeout_seconds,
                poll_interval_seconds=self.settings.poll_interval_seconds,
            )
            status = (task.finish_status or "SUCCESS").upper()
            result = DependencyResult(task_id, status, task.finish_message)
        except PredecessorCanceledError as exc:
            result = DependencyResult(task_id, "CANCELED", str(exc))
        except PredecessorTimeoutError as exc:
            result = DependencyResult(task_id, "TIMEOUT", str(exc))
        except PredecessorFailedError as exc:
            result = DependencyResult(task_id, "FAILED", str(exc))
        self.logger.info(
            "predecessor concluido task_id=%s status=%s", task_id, result.status
        )
        return result


__all__ = [
    "CAPSTONE_BOT_LABELS",
    "CapstoneContext",
    "CapstoneOrchestrationSettings",
    "CapstoneOrchestrator",
    "CapstoneOutcome",
    "CapstoneStage",
    "DependencyResult",
    "PipelineManifest",
]
