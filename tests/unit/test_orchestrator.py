from __future__ import annotations

from dataclasses import replace

import pytest

from src.maestro_client import InMemoryMaestroGateway, MaestroTask
from src.orchestrator import (
    BOT_LABELS,
    BotStage,
    OrchestrationContext,
    StageResult,
    resolve_stage,
    run_orchestrated_stage,
)
from src.wait_for_predecessor import (
    PredecessorFailedError,
    PredecessorTimeoutError,
    wait_for_predecessor,
)

pytestmark = pytest.mark.unit


def test_resolve_stage_usa_labels_exigidos_pela_issue():
    assert resolve_stage("rebecca-dispatcher-v1") is BotStage.DISPATCHER
    assert resolve_stage("gabriel-conferencia-v1") is BotStage.CONFERENCE
    assert resolve_stage("marcelo-relatorio-v1") is BotStage.REPORT

    with pytest.raises(ValueError, match="BOT_ID não identifica"):
        resolve_stage("bot-desconhecido")


def test_contexto_raiz_gera_correlacao_e_identifica_disparo_manual():
    context = OrchestrationContext.from_parameters(
        BotStage.DISPATCHER,
        "task-a",
        {},
        correlation_factory=lambda: "corr-001",
    )

    assert context.correlation_id == "corr-001"
    assert context.root_task_id == "task-a"
    assert context.parent_task_id is None
    assert context.trigger_bot == "maestro"


def test_contexto_dependente_exige_toda_a_rastreabilidade():
    parameters = {
        "correlation_id": "corr-001",
        "root_task_id": "task-a",
        "parent_task_id": "task-a",
        "trigger_bot": BOT_LABELS[BotStage.DISPATCHER],
        "previous_result": {"status": "SUCCESS"},
    }

    context = OrchestrationContext.from_parameters(
        BotStage.CONFERENCE,
        "task-b",
        parameters,
    )

    assert context.previous_result == {"status": "SUCCESS"}
    assert context.parent_task_id == "task-a"

    for field_name in (
        "correlation_id",
        "root_task_id",
        "parent_task_id",
        "trigger_bot",
    ):
        incomplete = dict(parameters)
        incomplete.pop(field_name)
        with pytest.raises(ValueError, match=field_name):
            OrchestrationContext.from_parameters(
                BotStage.CONFERENCE,
                "task-b",
                incomplete,
            )


def test_stage_result_rejeita_status_contador_e_payload_invalidos():
    with pytest.raises(ValueError, match="Status"):
        StageResult("RUNNING", "incompleto")
    with pytest.raises(ValueError, match="negativos"):
        StageResult("SUCCESS", "ok", failed_items=-1)
    with pytest.raises(TypeError):
        StageResult("SUCCESS", "ok", payload={"value": object()})
    with pytest.raises(ValueError, match="message"):
        StageResult("FAILED", "   ")


class AdvancingClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_wait_for_predecessor_retorna_sucesso_terminal():
    gateway = InMemoryMaestroGateway("task-a")
    gateway.finish_task("SUCCESS", "ok", 1, 1, 0)

    task = wait_for_predecessor(
        gateway,
        "task-a",
        timeout_seconds=10,
        poll_interval_seconds=1,
    )

    assert task.finish_status == "SUCCESS"


@pytest.mark.parametrize(
    ("state", "finish_status", "message"),
    [
        ("FINISHED", "FAILED", "falha no dispatcher"),
        ("CANCELED", None, ""),
    ],
)
def test_wait_for_predecessor_rejeita_falha_ou_cancelamento(
    state,
    finish_status,
    message,
):
    gateway = InMemoryMaestroGateway("task-a")
    gateway.tasks["task-a"] = MaestroTask(
        task_id="task-a",
        state=state,
        parameters={},
        finish_status=finish_status,
        finish_message=message,
    )

    with pytest.raises(PredecessorFailedError, match="task-a"):
        wait_for_predecessor(
            gateway,
            "task-a",
            timeout_seconds=10,
            poll_interval_seconds=1,
        )


def test_wait_for_predecessor_interrompe_no_timeout():
    gateway = InMemoryMaestroGateway("task-a")
    clock = AdvancingClock()

    with pytest.raises(PredecessorTimeoutError, match="Timeout.*task-a.*3s"):
        wait_for_predecessor(
            gateway,
            "task-a",
            timeout_seconds=3,
            poll_interval_seconds=1,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

    assert clock.value == 3


def test_orchestrador_cria_proxima_task_com_contexto_completo():
    gateway = InMemoryMaestroGateway("task-a")

    outcome = run_orchestrated_stage(
        BotStage.DISPATCHER,
        gateway,
        lambda context: StageResult(
            "SUCCESS",
            "16 itens publicados",
            payload={"published_items": 16},
            total_items=16,
            processed_items=16,
        ),
        timeout_seconds=10,
        poll_interval_seconds=1,
        correlation_factory=lambda: "corr-001",
    )

    assert outcome.result.status == "SUCCESS"
    assert outcome.next_task_id == "local-child-1"
    child = gateway.get_task(outcome.next_task_id)
    assert child.activity_label == BOT_LABELS[BotStage.CONFERENCE]
    assert child.parameters == {
        "correlation_id": "corr-001",
        "root_task_id": "task-a",
        "parent_task_id": "task-a",
        "trigger_bot": BOT_LABELS[BotStage.DISPATCHER],
        "previous_result": outcome.result.to_dict(),
    }
    assert gateway.get_task("task-a").finish_status == "SUCCESS"
    assert gateway.orchestration_events == [
        ("create_task", "local-child-1"),
        ("finish_task", "task-a"),
    ]


def test_orchestrador_finaliza_falha_sem_criar_proxima_task():
    gateway = InMemoryMaestroGateway("task-a")

    outcome = run_orchestrated_stage(
        BotStage.DISPATCHER,
        gateway,
        lambda context: StageResult("FAILED", "CSV inválido"),
        timeout_seconds=10,
        poll_interval_seconds=1,
    )

    assert outcome.result.status == "FAILED"
    assert outcome.next_task_id is None
    assert gateway.get_task("task-a").finish_status == "FAILED"
    assert len(gateway.tasks) == 1


def test_orchestrador_finaliza_task_quando_excecao_nao_tem_mensagem():
    gateway = InMemoryMaestroGateway("task-a")

    def fail_without_message(context):
        raise RuntimeError

    outcome = run_orchestrated_stage(
        BotStage.DISPATCHER,
        gateway,
        fail_without_message,
        timeout_seconds=10,
        poll_interval_seconds=1,
    )

    assert outcome.result.status == "FAILED"
    assert outcome.result.message == "RuntimeError sem mensagem"
    assert gateway.get_task("task-a").finish_status == "FAILED"
    assert gateway.get_task("task-a").finish_message == outcome.result.message


def test_activate_task_preserva_parametros_da_task_criada():
    gateway = InMemoryMaestroGateway("task-a")
    child = gateway.create_task("bot-b", {"correlation_id": "corr-001"})

    gateway.activate_task(child.task_id)

    assert gateway.current_task_id == child.task_id
    assert gateway.get_task(child.task_id) == replace(child, state="RUNNING")
