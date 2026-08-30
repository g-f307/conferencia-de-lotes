from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.capstone_orchestrator import (
    CAPSTONE_BOT_LABELS,
    CapstoneOrchestrationSettings,
    CapstoneOrchestrator,
    CapstoneStage,
)
from src.maestro_client import InMemoryMaestroGateway, MaestroTask
from src.orchestrator import StageResult
from src.smart_office import SmartOfficeGatewayAdapter
from src.wait_for_predecessor import (
    PredecessorCanceledError,
    PredecessorFailedError,
    PredecessorTimeoutError,
)

pytestmark = pytest.mark.unit


def _settings() -> CapstoneOrchestrationSettings:
    return CapstoneOrchestrationSettings(
        desktop_priority=90,
        default_priority=40,
        dependency_timeout_seconds=10,
        poll_interval_seconds=0.1,
    )


def test_schedule_cria_seis_bots_com_fan_out_fan_in_e_prioridade() -> None:
    gateway = InMemoryMaestroGateway("dispatcher-task")

    manifest = CapstoneOrchestrator(gateway, settings=_settings()).schedule(
        execution_id="exec-114", correlation_id="corr-114"
    )

    assert set(manifest.task_ids) == set(CapstoneStage)
    desktop = gateway.get_task(manifest.task_ids[CapstoneStage.DESKTOP])
    web = gateway.get_task(manifest.task_ids[CapstoneStage.WEB])
    consolidation = gateway.get_task(
        manifest.task_ids[CapstoneStage.CONSOLIDATION]
    )
    ml = gateway.get_task(manifest.task_ids[CapstoneStage.ML])
    report = gateway.get_task(manifest.task_ids[CapstoneStage.REPORT])
    assert desktop.activity_label == CAPSTONE_BOT_LABELS[CapstoneStage.DESKTOP]
    assert desktop.priority == 90
    assert web.priority == 40
    assert desktop.predecessor_task_ids == ("dispatcher-task",)
    assert web.predecessor_task_ids == ("dispatcher-task",)
    assert consolidation.predecessor_task_ids == (desktop.task_id, web.task_id)
    assert ml.predecessor_task_ids == (consolidation.task_id,)
    assert report.predecessor_task_ids == (ml.task_id,)
    assert all(
        gateway.get_task(task_id).timeout_seconds == 10
        for stage, task_id in manifest.task_ids.items()
        if stage is not CapstoneStage.DISPATCHER
    )
    assert gateway.finished_tasks[-1][0] == "SUCCESS"


def test_contexto_propaga_identificadores_em_todas_as_tasks() -> None:
    gateway = InMemoryMaestroGateway("root")
    manifest = CapstoneOrchestrator(gateway, settings=_settings()).schedule(
        execution_id="exec", correlation_id="corr"
    )

    for stage, task_id in manifest.task_ids.items():
        if stage is CapstoneStage.DISPATCHER:
            continue
        parameters = gateway.get_task(task_id).parameters
        assert parameters["execution_id"] == "exec"
        assert parameters["correlation_id"] == "corr"
        assert parameters["root_task_id"] == "root"
        assert parameters["parent_task_id"] == "root"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PredecessorFailedError("erro"), "FAILED"),
        (PredecessorCanceledError("cancelada"), "CANCELED"),
        (PredecessorTimeoutError("timeout"), "TIMEOUT"),
    ],
)
def test_dependencias_distinguem_erro_cancelamento_e_timeout(
    error: Exception, expected: str
) -> None:
    gateway = InMemoryMaestroGateway("root")
    manifest = CapstoneOrchestrator(gateway, settings=_settings()).schedule()
    gateway.activate_task(manifest.task_ids[CapstoneStage.ML])

    def fail_wait(*args: object, **kwargs: object) -> MaestroTask:
        raise error

    outcome = CapstoneOrchestrator(
        gateway, settings=_settings(), wait_function=fail_wait
    ).execute_current(CapstoneStage.ML, lambda context: StageResult("SUCCESS", "ok"))

    assert outcome.context.dependency_results[0].status == expected
    assert outcome.result.status == "FAILED"


def test_relatorio_continua_em_modo_degradado_quando_ml_falha() -> None:
    gateway = InMemoryMaestroGateway("root")
    manifest = CapstoneOrchestrator(gateway, settings=_settings()).schedule()
    gateway.activate_task(manifest.task_ids[CapstoneStage.REPORT])
    called = False

    def fail_wait(*args: object, **kwargs: object) -> MaestroTask:
        raise PredecessorFailedError("ML indisponivel")

    def report(context: object) -> StageResult:
        nonlocal called
        called = True
        return StageResult("SUCCESS", "relatorio de incidente gerado")

    outcome = CapstoneOrchestrator(
        gateway, settings=_settings(), wait_function=fail_wait
    ).execute_current(CapstoneStage.REPORT, report)

    assert called
    assert outcome.result.status == "PARTIALLY_COMPLETED"


@dataclass
class _SmartTask:
    id: str
    activity_label: str
    state: str = "CREATED"
    parameters: dict[str, object] | None = None


class _SmartClient:
    current_task_id = "smart-root"

    def __init__(self) -> None:
        self.received: dict[str, object] = {}

    def create_task(self, activity_label, parameters, **kwargs):
        self.received = {"label": activity_label, "parameters": parameters, **kwargs}
        return _SmartTask("smart-child", activity_label, parameters=parameters)

    def get_task(self, task_id):
        return _SmartTask(task_id, "bot")

    def finish_task(self, *args):
        self.finished = args


def test_adapter_smart_office_encaminha_metadados_de_agendamento() -> None:
    client = _SmartClient()
    gateway = SmartOfficeGatewayAdapter(client)

    task = gateway.create_task(
        "bot",
        {"correlation_id": "corr"},
        priority=80,
        predecessor_task_ids=("a", "b"),
        timeout_seconds=30,
    )

    assert task.task_id == "smart-child"
    assert task.priority == 80
    assert task.predecessor_task_ids == ("a", "b")
    assert client.received["timeout_seconds"] == 30


class _RejectingGateway(InMemoryMaestroGateway):
    def __init__(self, rejected_labels: set[str]) -> None:
        super().__init__("root")
        self.rejected_labels = rejected_labels

    def create_task(self, activity_label, parameters, **kwargs):
        if activity_label in self.rejected_labels:
            raise RuntimeError("rejeicao controlada")
        return super().create_task(activity_label, parameters, **kwargs)


def test_falha_de_criacao_de_uma_coleta_vira_dependencia_sintetica() -> None:
    desktop_label = CAPSTONE_BOT_LABELS[CapstoneStage.DESKTOP]
    gateway = _RejectingGateway({desktop_label})
    manifest = CapstoneOrchestrator(gateway, settings=_settings()).schedule()
    web_id = manifest.task_ids[CapstoneStage.WEB]
    gateway.activate_task(web_id)
    gateway.finish_task("SUCCESS", "coleta web concluida", 1, 1, 0)
    gateway.activate_task(manifest.task_ids[CapstoneStage.CONSOLIDATION])

    outcome = CapstoneOrchestrator(gateway, settings=_settings()).execute_current(
        CapstoneStage.CONSOLIDATION,
        lambda context: StageResult("SUCCESS", "consolidacao degradada"),
    )

    assert outcome.result.status == "PARTIALLY_COMPLETED"
    assert len(outcome.context.dependency_results) == 2
    synthetic = next(
        result for result in outcome.context.dependency_results if result.synthetic
    )
    assert synthetic.task_id is None
    assert synthetic.status == "FAILED"
    assert synthetic.source_alias == desktop_label
    assert synthetic.source_status == "UNAVAILABLE"
    assert synthetic.motivo_fallback == "task_creation_failed"


def test_falha_de_criacao_das_duas_coletas_gera_incidente() -> None:
    collector_labels = {
        CAPSTONE_BOT_LABELS[CapstoneStage.DESKTOP],
        CAPSTONE_BOT_LABELS[CapstoneStage.WEB],
    }
    gateway = _RejectingGateway(collector_labels)
    manifest = CapstoneOrchestrator(gateway, settings=_settings()).schedule()
    consolidation_id = manifest.task_ids[CapstoneStage.CONSOLIDATION]
    assert gateway.get_task(consolidation_id).predecessor_task_ids == ()
    gateway.activate_task(consolidation_id)

    outcome = CapstoneOrchestrator(gateway, settings=_settings()).execute_current(
        CapstoneStage.CONSOLIDATION,
        lambda context: StageResult("SUCCESS", "snapshot sintetico"),
    )

    assert len(outcome.context.dependency_results) == 2
    assert all(result.synthetic for result in outcome.context.dependency_results)
    assert all(
        result.source_status == "UNAVAILABLE"
        for result in outcome.context.dependency_results
    )
    assert outcome.result.status == "FAILED"
    assert outcome.result.payload["report_type"] == "OPERATIONAL_INCIDENT"
    assert outcome.result.payload["snapshot_type"] == "OPERATIONAL_FAILURE"
