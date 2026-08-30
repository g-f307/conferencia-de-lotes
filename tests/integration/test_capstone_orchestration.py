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

pytestmark = pytest.mark.integration


def test_pipeline_dos_seis_bots_mantem_relatorio_apos_falha_do_ml() -> None:
    gateway = InMemoryMaestroGateway("dispatcher")
    settings = CapstoneOrchestrationSettings(
        desktop_priority=100,
        default_priority=50,
        dependency_timeout_seconds=1,
        poll_interval_seconds=0.01,
    )
    orchestrator = CapstoneOrchestrator(gateway, settings=settings)
    manifest = orchestrator.schedule(execution_id="exec-e2e", correlation_id="corr-e2e")

    def run(stage: CapstoneStage, status: str = "SUCCESS") -> None:
        gateway.activate_task(manifest.task_ids[stage])
        CapstoneOrchestrator(gateway, settings=settings).execute_current(
            stage, lambda context: StageResult(status, f"{stage.value} concluido")
        )

    run(CapstoneStage.DESKTOP)
    run(CapstoneStage.WEB)
    run(CapstoneStage.CONSOLIDATION)
    run(CapstoneStage.ML, "FAILED")
    run(CapstoneStage.REPORT)

    report = gateway.get_task(manifest.task_ids[CapstoneStage.REPORT])
    assert report.finish_status == "PARTIALLY_COMPLETED"
    assert {task.activity_label for task in gateway.tasks.values()} >= {
        "estoque-desktop-v1",
        "fornecedores-web-v1",
        "consolidacao-v2",
        "classificador-ml-v1",
        "relatorio-alertas-v2",
    }


def test_consolidacao_aguarda_as_duas_coletas_antes_de_executar() -> None:
    gateway = InMemoryMaestroGateway("dispatcher")
    settings = CapstoneOrchestrationSettings(
        desktop_priority=100,
        default_priority=50,
        dependency_timeout_seconds=0.01,
        poll_interval_seconds=0.005,
    )
    manifest = CapstoneOrchestrator(gateway, settings=settings).schedule()
    desktop_id = manifest.task_ids[CapstoneStage.DESKTOP]
    web_id = manifest.task_ids[CapstoneStage.WEB]
    gateway.tasks[desktop_id] = replace(
        gateway.get_task(desktop_id), state="FINISHED", finish_status="SUCCESS"
    )
    gateway.activate_task(manifest.task_ids[CapstoneStage.CONSOLIDATION])

    outcome = CapstoneOrchestrator(gateway, settings=settings).execute_current(
        CapstoneStage.CONSOLIDATION,
        lambda context: StageResult("SUCCESS", "snapshot degradado"),
    )

    assert [result.task_id for result in outcome.context.dependency_results] == [
        desktop_id,
        web_id,
    ]
    assert [result.status for result in outcome.context.dependency_results] == [
        "SUCCESS",
        "TIMEOUT",
    ]
    assert outcome.result.status == "PARTIALLY_COMPLETED"
