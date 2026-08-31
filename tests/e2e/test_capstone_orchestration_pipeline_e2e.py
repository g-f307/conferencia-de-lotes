from __future__ import annotations

from dataclasses import replace

import pytest

from src.capstone_orchestrator import (
    CapstoneOrchestrationSettings,
    CapstoneOrchestrator,
    CapstoneStage,
)
from src.maestro_client import InMemoryMaestroGateway
from src.orchestrator import StageResult

pytestmark = pytest.mark.e2e


def test_pipeline_capstone_executa_seis_bots_sem_smart_office_real() -> None:
    gateway = InMemoryMaestroGateway("dispatcher-capstone")
    settings = CapstoneOrchestrationSettings(
        desktop_priority=100,
        default_priority=50,
        dependency_timeout_seconds=1,
        poll_interval_seconds=0.01,
    )
    manifest = CapstoneOrchestrator(gateway, settings=settings).schedule(
        execution_id="exec-controlada", correlation_id="corr-controlada"
    )

    for stage in (
        CapstoneStage.DESKTOP,
        CapstoneStage.WEB,
        CapstoneStage.CONSOLIDATION,
        CapstoneStage.ML,
        CapstoneStage.REPORT,
    ):
        gateway.activate_task(manifest.task_ids[stage])
        outcome = CapstoneOrchestrator(gateway, settings=settings).execute_current(
            stage, lambda context: StageResult("SUCCESS", "etapa concluida")
        )
        assert outcome.context.execution_id == "exec-controlada"
        assert outcome.context.correlation_id == "corr-controlada"
        assert outcome.result.status == "SUCCESS"

    assert len(manifest.task_ids) == 6
    assert all(task.state == "FINISHED" for task in gateway.tasks.values())


def test_pipeline_continua_ate_relatorio_quando_desktop_cai() -> None:
    gateway = InMemoryMaestroGateway("dispatcher-capstone")
    settings = CapstoneOrchestrationSettings(
        desktop_priority=100,
        default_priority=50,
        dependency_timeout_seconds=1,
        poll_interval_seconds=0.01,
    )
    orchestrator = CapstoneOrchestrator(gateway, settings=settings)
    manifest = orchestrator.schedule(
        execution_id="exec-desktop-indisponivel",
        correlation_id="corr-desktop-indisponivel",
    )
    desktop_id = manifest.task_ids[CapstoneStage.DESKTOP]
    web_id = manifest.task_ids[CapstoneStage.WEB]
    gateway.tasks[desktop_id] = replace(
        gateway.get_task(desktop_id),
        state="FINISHED",
        finish_status="FAILED",
        finish_message="queda controlada da coleta desktop",
    )
    gateway.tasks[web_id] = replace(
        gateway.get_task(web_id),
        state="FINISHED",
        finish_status="SUCCESS",
        finish_message="coleta web concluida",
    )

    gateway.activate_task(manifest.task_ids[CapstoneStage.CONSOLIDATION])
    consolidation = orchestrator.execute_current(
        CapstoneStage.CONSOLIDATION,
        lambda context: StageResult("SUCCESS", "snapshot degradado gerado"),
    )
    assert [item.status for item in consolidation.context.dependency_results] == [
        "FAILED",
        "SUCCESS",
    ]
    assert consolidation.result.status == "PARTIALLY_COMPLETED"

    for stage in (CapstoneStage.ML, CapstoneStage.REPORT):
        gateway.activate_task(manifest.task_ids[stage])
        orchestrator.execute_current(
            stage,
            lambda context: StageResult(
                "PARTIALLY_COMPLETED",
                "continuidade degradada",
            ),
        )

    report = gateway.get_task(manifest.task_ids[CapstoneStage.REPORT])
    assert report.state == "FINISHED"
    assert report.finish_status == "PARTIALLY_COMPLETED"
