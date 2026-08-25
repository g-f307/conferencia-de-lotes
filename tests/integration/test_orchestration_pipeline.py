from __future__ import annotations

import json
import logging
from dataclasses import replace

import pytest

from src.config import Settings
from src.logging_config import configure_logging
from src.maestro_client import InMemoryMaestroGateway, MaestroClient
from src.orchestrator import (
    BOT_LABELS,
    BotStage,
    StageResult,
    run_default_orchestration,
    run_orchestrated_stage,
)
from src.wait_for_predecessor import PredecessorTimeoutError

pytestmark = pytest.mark.integration


def test_pipeline_encadeia_tres_bots_com_correlacao_ponta_a_ponta():
    gateway = InMemoryMaestroGateway("task-a")
    observed_contexts = []

    def dispatcher(context):
        observed_contexts.append(context)
        return StageResult(
            "SUCCESS",
            "itens publicados",
            payload={"published_items": 2},
            total_items=2,
            processed_items=2,
        )

    outcome_a = run_orchestrated_stage(
        BotStage.DISPATCHER,
        gateway,
        dispatcher,
        timeout_seconds=5,
        poll_interval_seconds=0.1,
        correlation_factory=lambda: "corr-pipeline",
    )
    gateway.activate_task(outcome_a.next_task_id)

    def conference(context):
        observed_contexts.append(context)
        assert context.previous_result["payload"] == {"published_items": 2}
        return StageResult(
            "PARTIALLY_COMPLETED",
            "conferência concluída",
            payload={
                "execution_result": {
                    "total_items": 2,
                    "processed_items": 1,
                    "failed_items": 1,
                    "ambiguous_items": 0,
                }
            },
            total_items=2,
            processed_items=1,
            failed_items=1,
        )

    outcome_b = run_orchestrated_stage(
        BotStage.CONFERENCE,
        gateway,
        conference,
        timeout_seconds=5,
        poll_interval_seconds=0.1,
    )
    gateway.activate_task(outcome_b.next_task_id)

    def report(context):
        observed_contexts.append(context)
        assert context.previous_result["status"] == "PARTIALLY_COMPLETED"
        return StageResult(
            "SUCCESS",
            "relatório publicado",
            payload={"artifact": "resumo_execucao.json"},
            total_items=2,
            processed_items=1,
            failed_items=1,
        )

    outcome_c = run_orchestrated_stage(
        BotStage.REPORT,
        gateway,
        report,
        timeout_seconds=5,
        poll_interval_seconds=0.1,
    )

    context_a, context_b, context_c = observed_contexts
    assert outcome_c.next_task_id is None
    assert {context.correlation_id for context in observed_contexts} == {
        "corr-pipeline"
    }
    assert {context.root_task_id for context in observed_contexts} == {"task-a"}
    assert context_b.parent_task_id == context_a.current_task_id
    assert context_c.parent_task_id == context_b.current_task_id
    assert context_b.trigger_bot == BOT_LABELS[BotStage.DISPATCHER]
    assert context_c.trigger_bot == BOT_LABELS[BotStage.CONFERENCE]
    assert gateway.get_task(context_a.current_task_id).finish_status == "SUCCESS"
    assert (
        gateway.get_task(context_b.current_task_id).finish_status
        == "PARTIALLY_COMPLETED"
    )
    assert gateway.get_task(context_c.current_task_id).finish_status == "SUCCESS"


def test_falha_do_predecessor_impede_handler_e_finaliza_dependente():
    gateway = InMemoryMaestroGateway("task-a")
    child = gateway.create_task(
        BOT_LABELS[BotStage.CONFERENCE],
        {
            "correlation_id": "corr-falha",
            "root_task_id": "task-a",
            "parent_task_id": "task-a",
            "trigger_bot": BOT_LABELS[BotStage.DISPATCHER],
            "previous_result": {"status": "FAILED"},
        },
    )
    gateway.finish_task("FAILED", "CSV inválido", 0, 0, 1)
    gateway.activate_task(child.task_id)
    handler_called = False

    def handler(context):
        nonlocal handler_called
        handler_called = True
        return StageResult("SUCCESS", "não deveria executar")

    outcome = run_orchestrated_stage(
        BotStage.CONFERENCE,
        gateway,
        handler,
        timeout_seconds=5,
        poll_interval_seconds=0.1,
    )

    assert handler_called is False
    assert outcome.result.status == "FAILED"
    assert "CSV inválido" in outcome.result.message
    assert gateway.get_task(child.task_id).finish_status == "FAILED"
    assert len(gateway.tasks) == 2


def test_timeout_do_predecessor_finaliza_dependente_sem_executar_handler():
    gateway = InMemoryMaestroGateway("task-a")
    child = gateway.create_task(
        BOT_LABELS[BotStage.CONFERENCE],
        {
            "correlation_id": "corr-timeout",
            "root_task_id": "task-a",
            "parent_task_id": "task-a",
            "trigger_bot": BOT_LABELS[BotStage.DISPATCHER],
            "previous_result": {"status": "SUCCESS"},
        },
    )
    gateway.activate_task(child.task_id)
    handler_called = False

    def handler(context):
        nonlocal handler_called
        handler_called = True
        return StageResult("SUCCESS", "não deveria executar")

    def timeout(*args, **kwargs):
        raise PredecessorTimeoutError("Timeout ao aguardar task-a após 5s")

    outcome = run_orchestrated_stage(
        BotStage.CONFERENCE,
        gateway,
        handler,
        timeout_seconds=5,
        poll_interval_seconds=0.1,
        wait_fn=timeout,
    )

    assert handler_called is False
    assert outcome.result.status == "FAILED"
    assert outcome.result.message == "Timeout ao aguardar task-a após 5s"
    assert gateway.get_task(child.task_id).finish_status == "FAILED"
    assert gateway.get_task(child.task_id).finish_message == outcome.result.message


def test_label_de_atividade_invalido_finaliza_task_com_falha(tmp_path):
    settings = replace(
        Settings.from_env(tmp_path),
        maestro_enabled=False,
        vault_enabled=False,
        web_automation_enabled=False,
        ml_enabled=False,
        orchestration_enabled=False,
        bot_id="bot-generico",
    )
    gateway = InMemoryMaestroGateway("task-invalida")
    gateway.tasks["task-invalida"] = replace(
        gateway.tasks["task-invalida"],
        activity_label="atividade-invalida",
    )
    client = MaestroClient(settings, gateway=gateway)

    outcome = run_default_orchestration(settings, maestro_client=client)

    assert outcome.context is None
    assert outcome.result.status == "FAILED"
    assert "BOT_ID não identifica um estágio" in outcome.result.message
    assert gateway.tasks["task-invalida"].state == "FINISHED"
    assert gateway.tasks["task-invalida"].finish_status == "FAILED"
    assert gateway.finished_tasks[-1][0] == "FAILED"
    last_record = json.loads(
        settings.log_file.read_text(encoding="utf-8").splitlines()[-1]
    )
    assert last_record["evento"] == "FIM_BOT"
    assert last_record["detalhes"]["status"] == "FAILED"
    assert last_record["detalhes"]["current_task_id"] == "task-invalida"


def test_falha_ao_consultar_task_finaliza_execucao_com_falha(
    tmp_path,
    monkeypatch,
):
    settings = replace(
        Settings.from_env(tmp_path),
        maestro_enabled=False,
        vault_enabled=False,
        web_automation_enabled=False,
        ml_enabled=False,
        orchestration_enabled=False,
        bot_id=BOT_LABELS[BotStage.DISPATCHER],
    )
    gateway = InMemoryMaestroGateway("task-consulta")
    client = MaestroClient(settings, gateway=gateway)

    def fail_lookup(task_id):
        raise RuntimeError("Maestro indisponível durante consulta")

    monkeypatch.setattr(gateway, "get_task", fail_lookup)

    outcome = run_default_orchestration(settings, maestro_client=client)

    assert outcome.context is None
    assert outcome.result.status == "FAILED"
    assert outcome.result.message == "Maestro indisponível durante consulta"
    assert gateway.tasks["task-consulta"].state == "FINISHED"
    assert gateway.tasks["task-consulta"].finish_status == "FAILED"
    assert gateway.finished_tasks[-1][0] == "FAILED"


def test_pipeline_real_publica_processa_e_gera_relatorios_sem_maestro(tmp_path):
    input_dir = tmp_path / "dados_entrada"
    input_dir.mkdir()
    input_csv = input_dir / "lotes.csv"
    input_csv.write_text(
        "lote_id,produto,linha,turno,status,responsavel,data,observacao\n"
        "L001,Monitor,Linha A,Manha,APROVADO,Marcelo,2026-08-25,\n",
        encoding="utf-8",
    )
    base_settings = replace(
        Settings.from_env(tmp_path),
        maestro_enabled=False,
        vault_enabled=False,
        web_automation_enabled=False,
        ml_enabled=False,
        orchestration_enabled=False,
        bot_id="bot-conferencia-de-lotes-v2",
        execution_id="execucao-compartilhada",
        input_dir=input_dir,
        input_csv=input_csv,
        reference_lotes=("L001",),
        processing_delay_seconds=0,
    )
    logger = logging.getLogger("orchestration-pipeline-test")
    gateway = InMemoryMaestroGateway("task-a")
    gateway.tasks["task-a"] = replace(
        gateway.get_task("task-a"),
        activity_label=BOT_LABELS[BotStage.DISPATCHER],
    )
    client = MaestroClient(base_settings, gateway=gateway)

    outcome_a = run_default_orchestration(
        base_settings,
        maestro_client=client,
        logger=logger,
    )
    gateway.activate_task(outcome_a.next_task_id)

    outcome_b = run_default_orchestration(
        base_settings,
        maestro_client=client,
        logger=logger,
    )
    gateway.activate_task(outcome_b.next_task_id)

    outcome_c = run_default_orchestration(
        base_settings,
        maestro_client=client,
        logger=logger,
    )

    assert outcome_a.result.payload["published_items"] == 1
    assert outcome_b.result.total_items == 1
    assert outcome_b.result.processed_items == 1
    assert outcome_c.result.status == "SUCCESS"
    assert (base_settings.report_dir / "resumo_execucao.json").is_file()
    assert (base_settings.report_dir / "relatorio_evidencias.pdf").is_file()
    assert [task.activity_label for task in gateway.tasks.values()] == [
        BOT_LABELS[BotStage.DISPATCHER],
        BOT_LABELS[BotStage.CONFERENCE],
        BOT_LABELS[BotStage.REPORT],
    ]
    assert len({
        task.parameters.get("correlation_id")
        for task in gateway.tasks.values()
        if task.parameters
    }) == 1
    assert gateway.info_alerts[-1].endswith("relatório publicado")


def test_logs_da_orquestracao_permitem_reconstruir_a_task_criada(tmp_path):
    settings = replace(
        Settings.from_env(tmp_path),
        bot_id=BOT_LABELS[BotStage.DISPATCHER],
        execution_id="task-a",
    )
    logger = configure_logging(settings.log_file, settings)
    gateway = InMemoryMaestroGateway("task-a")

    outcome = run_orchestrated_stage(
        BotStage.DISPATCHER,
        gateway,
        lambda context: StageResult("SUCCESS", "publicação concluída"),
        timeout_seconds=5,
        poll_interval_seconds=0.1,
        logger=logger,
        correlation_factory=lambda: "corr-log",
    )

    records = [
        json.loads(line)
        for line in settings.log_file.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["evento"] for record in records] == [
        "INICIO_BOT",
        "PROXIMA_TASK_CRIADA",
        "FIM_BOT",
    ]
    assert all(
        record["detalhes"]["correlation_id"] == "corr-log"
        for record in records
    )
    created = records[1]["detalhes"]
    assert created["root_task_id"] == "task-a"
    assert created["current_task_id"] == "task-a"
    assert created["trigger_bot"] == "maestro"
    assert created["orchestration_stage"] == "dispatcher"
    assert created["next_task_id"] == outcome.next_task_id
