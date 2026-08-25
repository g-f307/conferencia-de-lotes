"""Sabotagens deterministicas exigidas pelo estudo de caso S10-B."""

from __future__ import annotations

import json

import pytest

from src.alerts import Alerta, CanalLogLocal, Severidade, SistemaAlertas
from src.bot import LotePerformer
from src.classificador_divergencia import (
    ClassificadorDivergencia,
    PredicaoCausa,
)
from src.dead_letter import DeadLetterWriter
from src.item_processor import ItemProcessor
from src.logging_config import configure_logging
from src.maestro_client import InMemoryMaestroGateway
from src.ml_audit import MLDecisionRecorder
from src.orchestrator import BotStage, StageResult, run_orchestrated_stage
from src.reference_base import (
    ReferenceBaseService,
    ReferenceInfrastructureError,
)
from src.retry_policy import LinearRetryPolicy
from src.vault_client import VaultClient

pytestmark = pytest.mark.integration


def controlled_item(index: int, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "lote_id": f"L{index:03d}",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manha",
        "status": "EM ANALISE",
        "responsavel": "Equipe S10-B",
        "data": "2026-08-25",
        "observacao": f"Conferencia controlada {index}",
    }
    item.update(overrides)
    return item


class CrisisQueue:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = list(items)
        self.done = []
        self.reviews = []
        self.business_errors = []
        self.system_errors = []

    def has_next(self) -> bool:
        return bool(self.items)

    def next(self):
        return self.items.pop(0)

    def mark_done(self, item, result) -> None:
        self.done.append((item, result))

    def mark_human_review(self, item, review, result) -> None:
        self.reviews.append((item, review, result))

    def mark_business_error(self, item, error, result) -> None:
        self.business_errors.append((item, error, result))

    def mark_system_error(self, item, error, result) -> None:
        self.system_errors.append((item, error, result))

    @property
    def terminal_count(self) -> int:
        return sum(
            map(
                len,
                (
                    self.done,
                    self.reviews,
                    self.business_errors,
                    self.system_errors,
                ),
            )
        )


class FakeVaultProvider:
    def get_credential(self, label):
        del label
        return {"username": "crise.erp", "password": "senha-efemera"}


class RecordingAlertGateway:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_error_alert(self, message: str) -> None:
        self.messages.append(message)


class OfflineReferenceGateway:
    def __init__(self) -> None:
        self.calls = 0

    def contains(self, lote_id: str, *, timeout_seconds: float) -> bool:
        del lote_id, timeout_seconds
        self.calls += 1
        raise ReferenceInfrastructureError("base offline; token=segredo-crise")


class SequenceMLProvider:
    def __init__(self, outcomes: list[PredicaoCausa | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.timeouts: list[float] = []

    def classificar(self, observacao: str, timeout_seconds: float) -> PredicaoCausa:
        del observacao
        self.timeouts.append(timeout_seconds)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class NotificationChannel:
    def __init__(self, nome: str, *, fail: bool = False) -> None:
        self.nome = nome
        self.fail = fail
        self.alerts: list[Alerta] = []

    def enviar(self, alerta: Alerta) -> None:
        self.alerts.append(alerta)
        if self.fail:
            raise RuntimeError("canal indisponivel; token=segredo-crise")


def emit_evidence(scenario: str, **details: object) -> None:
    print(
        "CRISIS_EVIDENCE "
        + json.dumps(
            {"cenario": scenario, **details},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def build_classifier(provider, *, confidence: float = 0.8, timeout: float = 0.2):
    return ClassificadorDivergencia(
        enabled=True,
        confianca_minima=confidence,
        timeout_seconds=timeout,
        provedor=provider,
    )


def test_crise_base_indisponivel_aplica_retry_alerta_e_conclui_lote(
    tmp_path,
):
    logger = configure_logging(tmp_path / "01-base-referencia.log")
    gateway = OfflineReferenceGateway()
    alerts = RecordingAlertGateway()
    sleeps: list[float] = []
    service = ReferenceBaseService(
        gateway,
        LinearRetryPolicy(3, 0.1, 0.5, sleep=sleeps.append),
        DeadLetterWriter(
            tmp_path / "dead_letter.jsonl",
            execution_id="crise-base",
            task_id="task-base",
        ),
        alert_gateway=alerts,
        logger=logger,
    )
    items = [controlled_item(index) for index in range(1, 4)]
    queue = CrisisQueue(items)
    processor = ItemProcessor(
        {item["lote_id"] for item in items},
        reference_base=service,
    )

    result = LotePerformer(
        queue,
        {item["lote_id"] for item in items},
        VaultClient(FakeVaultProvider()),
        item_processor=processor,
    ).run()

    log_content = (tmp_path / "01-base-referencia.log").read_text(
        encoding="utf-8"
    )
    assert result.total == queue.terminal_count == 3
    assert len(queue.reviews) == 3
    assert all(
        output["resultado_validacao"] == "PENDENTE_REVISAO"
        for _, _, output in queue.reviews
    )
    assert gateway.calls == 9
    assert sleeps == [0.1, 0.2] * 3
    assert len(alerts.messages) == 3
    assert "segredo-crise" not in log_content
    assert "[REDACTED]" in log_content
    assert not (tmp_path / "dead_letter.jsonl").exists()
    emit_evidence(
        "base_referencia_indisponivel",
        terminais=queue.terminal_count,
        tentativas=gateway.calls,
        alertas=len(alerts.messages),
        resultado="PENDENTE_REVISAO",
    )


def test_crise_ml_cai_durante_lote_e_classificador_direto_nao_lanca(tmp_path):
    logger = configure_logging(tmp_path / "02-ml-fora-do-ar.log")
    del logger
    provider = SequenceMLProvider(
        [
            PredicaoCausa("falha_calibracao", 0.95),
            OSError("servico ML fora do ar; token=segredo-crise"),
            PredicaoCausa("falha_sensor", 0.91),
        ]
    )
    items = [controlled_item(index) for index in range(1, 4)]
    queue = CrisisQueue(items)
    processor = ItemProcessor(
        {item["lote_id"] for item in items},
        divergence_classifier=build_classifier(provider),
        decision_recorder=MLDecisionRecorder("bot-crise", "exec-ml-offline"),
    )

    result = LotePerformer(
        queue,
        {item["lote_id"] for item in items},
        VaultClient(FakeVaultProvider()),
        item_processor=processor,
    ).run()

    direct = build_classifier(
        SequenceMLProvider([ConnectionError("ML desligado")])
    ).classificar("chamada direta com servico desligado")
    decisions = [decision.to_dict() for decision in result.ml_decisions]
    telegram = NotificationChannel("telegram")
    alerts = SistemaAlertas(
        telegram,
        NotificationChannel("email"),
        NotificationChannel("log_local"),
        logger=configure_logging(tmp_path / "02-alerta-sem-ml.log"),
    )
    all_fallback = alerts.avisar_pipeline_sem_ml(
        [
            {"origem_decisao": "fallback", "motivo_fallback": "indisponibilidade"}
            for _ in range(3)
        ],
        execution_id="exec-ml-offline",
        bot_id="bot-crise",
        estado_pipeline="PARTIALLY_COMPLETED",
    )

    log_content = (tmp_path / "02-ml-fora-do-ar.log").read_text(encoding="utf-8")
    assert result.total == queue.terminal_count == 3
    assert [decision["origem_decisao"] for decision in decisions] == [
        "ml",
        "fallback",
        "ml",
    ]
    assert decisions[1]["causa_provavel"] == "nao_classificado"
    assert decisions[1]["motivo_fallback"] == "indisponibilidade"
    assert direct.causa_provavel == "nao_classificado"
    assert direct.origem_decisao == "fallback"
    assert direct.motivo_fallback == "indisponibilidade"
    assert all_fallback is not None
    assert telegram.alerts[0].evento == "pipeline_operando_sem_ml"
    assert "segredo-crise" not in log_content
    emit_evidence(
        "ml_fora_do_ar_durante_lote",
        terminais=queue.terminal_count,
        origens=[decision["origem_decisao"] for decision in decisions],
        motivo=decisions[1]["motivo_fallback"],
    )


def test_crise_timeout_ml_respeita_limite_sem_espera_real_e_registra_motivo(
    tmp_path,
):
    configure_logging(tmp_path / "03-ml-timeout.log")
    provider = SequenceMLProvider([TimeoutError("timeout controlado")])
    clock_values = iter((10.0, 10.25))
    classifier = ClassificadorDivergencia(
        enabled=True,
        confianca_minima=0.8,
        timeout_seconds=0.25,
        provedor=provider,
        clock=lambda: next(clock_values),
    )

    result = classifier.classificar("observacao controlada")

    log_content = (tmp_path / "03-ml-timeout.log").read_text(encoding="utf-8")
    assert provider.timeouts == [0.25]
    assert result.origem_decisao == "fallback"
    assert result.motivo_fallback == "timeout"
    assert result.latencia_ms == 250
    assert "timeout" in log_content
    emit_evidence(
        "ml_timeout",
        timeout_configurado=provider.timeouts[0],
        latencia_simulada_ms=result.latencia_ms,
        motivo=result.motivo_fallback,
    )


def test_crise_baixa_confianca_descarta_sugestao_e_preserva_regras(tmp_path):
    configure_logging(tmp_path / "04-ml-baixa-confianca.log")
    provider = SequenceMLProvider([PredicaoCausa("causa_incerta", 0.49)])
    processor = ItemProcessor(
        {"L001"},
        divergence_classifier=build_classifier(provider, confidence=0.8),
        decision_recorder=MLDecisionRecorder("bot-crise", "exec-baixa-confianca"),
    )

    result = processor.process(controlled_item(1, produto=""))

    assert result.resultado == "DIVERGENCIA"
    assert result.mensagem.startswith("RN02")
    assert result.ml_decision is not None
    assert result.ml_decision.resultado_aplicado == "DIVERGENCIA"
    assert result.ml_decision.causa_provavel == "nao_classificado"
    assert result.ml_decision.origem_decisao == "fallback"
    assert result.ml_decision.motivo_fallback == "baixa_confianca"
    assert result.ml_decision.confianca_ml == 0.49
    emit_evidence(
        "ml_baixa_confianca",
        regra="RN02",
        resultado=result.resultado,
        origem=result.ml_decision.origem_decisao,
        motivo=result.ml_decision.motivo_fallback,
    )


def test_crise_telegram_invalido_entrega_email_ou_log_e_pipeline_conclui(
    tmp_path,
):
    queue = CrisisQueue([controlled_item(1, status="APROVADO")])
    pipeline = LotePerformer(
        queue,
        {"L001"},
        VaultClient(FakeVaultProvider()),
    ).run()
    telegram = NotificationChannel("telegram", fail=True)
    email = NotificationChannel("email")
    local_logger = configure_logging(tmp_path / "05-fallback-canais.log")
    local = CanalLogLocal(local_logger)
    alerts = SistemaAlertas(
        telegram,
        email,
        local,
        logger=local_logger,
    )
    alert = Alerta(
        severidade=Severidade.AVISO,
        execution_id="exec-canais",
        bot_id="bot-crise",
        quantidade_afetada=1,
        motivo_predominante="telegram_invalido",
        estado_pipeline="SUCCESS",
    )

    email_result = alerts.notificar(alert)
    all_failed_result = SistemaAlertas(
        NotificationChannel("telegram", fail=True),
        NotificationChannel("email", fail=True),
        local,
        logger=local_logger,
    ).notificar(alert)
    log_content = (tmp_path / "05-fallback-canais.log").read_text(
        encoding="utf-8"
    )

    assert pipeline.total == queue.terminal_count == 1
    assert pipeline.system_errors == 0
    assert email_result.entregues == ("email",)
    assert email_result.falhos == ("telegram",)
    assert all_failed_result.entregues == ("log_local",)
    assert all_failed_result.falhos == ("telegram", "email")
    assert "ALERTA LOCAL: perda de canal externo" in log_content
    assert "segredo-crise" not in log_content
    emit_evidence(
        "fallback_telegram_email",
        pipeline_terminal=queue.terminal_count,
        entrega_primaria=email_result.entregues,
        ultimo_recurso=all_failed_result.entregues,
    )


def test_crise_falha_repetida_de_dados_materializa_dead_letter(tmp_path):
    class InvalidDataGateway:
        def contains(self, lote_id: str, *, timeout_seconds: float):
            return {"lote_id": lote_id, "timeout": timeout_seconds}

    path = tmp_path / "data" / "output" / "dead_letter.jsonl"
    service = ReferenceBaseService(
        InvalidDataGateway(),
        LinearRetryPolicy(3, 0.1, 0.5, sleep=lambda seconds: None),
        DeadLetterWriter(
            path,
            execution_id="exec-dead-letter",
            task_id="task-dead-letter",
        ),
    )

    result = service.lookup(
        controlled_item(
            1,
            observacao="conteudo sigiloso",
            token="token-super-secreto",
        )
    )
    record = json.loads(path.read_text(encoding="utf-8"))

    assert result.status == "DATA_FAILURE"
    assert path.is_file()
    assert record["tentativas"] == 3
    assert record["execution_id"] == "exec-dead-letter"
    assert record["task_id"] == "task-dead-letter"
    assert "observacao" not in record["item"]
    assert "token" not in record["item"]
    assert "super-secreto" not in path.read_text(encoding="utf-8")


def test_crise_cadeia_de_task_id_permanece_reconstruivel():
    gateway = InMemoryMaestroGateway("task-a")
    contexts = []
    outcome = None

    for stage in (BotStage.DISPATCHER, BotStage.CONFERENCE, BotStage.REPORT):
        outcome = run_orchestrated_stage(
            stage,
            gateway,
            lambda context: (
                contexts.append(context)
                or StageResult("SUCCESS", f"{context.stage.value} concluido")
            ),
            timeout_seconds=1,
            poll_interval_seconds=0.01,
            correlation_factory=lambda: "corr-crise",
        )
        if outcome.next_task_id is not None:
            gateway.activate_task(outcome.next_task_id)

    assert outcome is not None
    assert outcome.next_task_id is None
    assert [context.current_task_id for context in contexts] == [
        "task-a",
        "local-child-1",
        "local-child-2",
    ]
    assert [context.parent_task_id for context in contexts] == [
        None,
        "task-a",
        "local-child-1",
    ]
    assert {context.correlation_id for context in contexts} == {"corr-crise"}
