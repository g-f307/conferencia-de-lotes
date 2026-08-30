from __future__ import annotations

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
