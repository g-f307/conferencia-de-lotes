"""Ensaio ponta a ponta com 30 itens e queda do ML durante o lote."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.alerts import ResultadoEntrega
from src.bot import LotePerformer
from src.capstone_reporting import CapstoneReportService
from src.classificador_divergencia import (
    ClassificadorDivergencia,
    PredicaoCausa,
)
from src.item_processor import ItemProcessor
from src.logging_config import configure_logging
from src.ml_audit import MLDecisionRecorder
from src.migration_control import (
    CoexistenceCoordinator,
    MigrationControlSettings,
    SQLiteLeaseStore,
)
from src.vault_client import VaultClient
from tests.capstone_crisis_support import (
    CrisisEvidenceWriter,
    CrisisScenario,
    LocalCapstonePipeline,
    assert_sanitized_evidence,
)

pytestmark = pytest.mark.e2e


def synthetic_item(index: int) -> dict[str, object]:
    return {
        "lote_id": f"L{index:03d}",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manha",
        "status": "EM ANALISE",
        "responsavel": "Equipe S10-B",
        "data": "2026-08-25",
        "observacao": f"Caso sintetico {index}",
    }


class TerminalQueue:
    def __init__(self, items) -> None:
        self.items = list(items)
        self.done = []
        self.reviews = []
        self.business_errors = []
        self.system_errors = []

    def has_next(self):
        return bool(self.items)

    def next(self):
        return self.items.pop(0)

    def mark_done(self, item, result):
        self.done.append((item, result))

    def mark_human_review(self, item, review, result):
        self.reviews.append((item, review, result))

    def mark_business_error(self, item, error, result):
        self.business_errors.append((item, error, result))

    def mark_system_error(self, item, error, result):
        self.system_errors.append((item, error, result))

    @property
    def terminal_count(self):
        return sum(
            len(group)
            for group in (
                self.done,
                self.reviews,
                self.business_errors,
                self.system_errors,
            )
        )


class FakeVaultProvider:
    def get_credential(self, label):
        del label
        return {"username": "ensaio.erp", "password": "senha-efemera"}


class MLDropDuringBatch:
    def __init__(self, available_calls: int) -> None:
        self.available_calls = available_calls
        self.calls = 0

    def classificar(self, observacao: str, timeout_seconds: float):
        del observacao, timeout_seconds
        self.calls += 1
        if self.calls > self.available_calls:
            raise ConnectionError("ML derrubado; token=segredo-que-nao-pode-vazar")
        return PredicaoCausa("falha_calibracao", 0.95)


def test_ensaio_de_crise_finaliza_os_30_casos_apos_queda_do_ml(tmp_path):
    log_file = tmp_path / "ensaio-crise-30-casos.log"
    configure_logging(log_file)
    items = [synthetic_item(index) for index in range(1, 31)]
    queue = TerminalQueue(items)
    provider = MLDropDuringBatch(available_calls=10)
    classifier = ClassificadorDivergencia(
        enabled=True,
        confianca_minima=0.8,
        timeout_seconds=0.2,
        provedor=provider,
    )
    processor = ItemProcessor(
        {item["lote_id"] for item in items},
        divergence_classifier=classifier,
        decision_recorder=MLDecisionRecorder("bot-crise", "exec-30-casos"),
    )

    result = LotePerformer(
        queue,
        {item["lote_id"] for item in items},
        VaultClient(FakeVaultProvider()),
        item_processor=processor,
    ).run()

    origins = [decision.origem_decisao for decision in result.ml_decisions]
    reasons = [decision.motivo_fallback for decision in result.ml_decisions]
    log_content = log_file.read_text(encoding="utf-8")
    evidence = {
        "cenario": "massa_sintetica_30_casos",
        "total": result.total,
        "terminais": queue.terminal_count,
        "ml": origins.count("ml"),
        "fallback": origins.count("fallback"),
        "motivo_fallback": "indisponibilidade",
        "erros_sistema": result.system_errors,
    }

    assert result.total == 30
    assert queue.terminal_count == 30
    assert len(queue.reviews) == 30
    assert result.system_errors == 0
    assert origins == ["ml"] * 10 + ["fallback"] * 20
    assert reasons[10:] == ["indisponibilidade"] * 20
    assert "segredo-que-nao-pode-vazar" not in log_content
    print("CRISIS_EVIDENCE " + json.dumps(evidence, sort_keys=True))


def _write_evidence(
    evidence_dir: Path,
    payload: dict[str, object],
) -> dict[str, object]:
    destination = CrisisEvidenceWriter(evidence_dir).write(payload)
    evidence = assert_sanitized_evidence(destination)
    print("CAPSTONE_CRISIS_EVIDENCE " + json.dumps(evidence, sort_keys=True))
    return evidence


@pytest.mark.browser
def test_capstone_base_indisponivel_conclui_pipeline_com_retry_e_alerta(
    tmp_path: Path,
    capstone_evidence_dir: Path,
) -> None:
    result = LocalCapstonePipeline(
        tmp_path / "base-offline",
        CrisisScenario.REFERENCE_UNAVAILABLE,
        real_web=True,
    ).run()

    assert len(result.manifest.task_ids) == 6
    assert result.reference_attempts == 12
    assert result.reference_alerts == 4
    assert {lookup.status.value for lookup in result.reference_results} == {
        "PENDENTE_REVISAO"
    }
    assert {
        record["status_operacional"]
        for record in result.consolidation_result["payload"]["records"]
    } == {"PENDENTE_REVISAO"}
    assert result.dead_letter_count == 0
    assert result.report_result.snapshot.processed_items == 4
    assert result.report_result.snapshot.modo_degradado
    assert result.report_result.snapshot.motivo_fallback == "fonte_indisponivel"
    assert all(
        state not in {"START", "RUNNING"}
        for state in result.local_task_states.values()
    )
    assert len(result.artifact_names) == 4
    _write_evidence(capstone_evidence_dir, result.evidence())


@pytest.mark.browser
def test_capstone_queda_ml_preserva_decisao_e_produz_relatorio(
    tmp_path: Path,
    capstone_evidence_dir: Path,
) -> None:
    result = LocalCapstonePipeline(
        tmp_path / "ml-offline",
        CrisisScenario.ML_UNAVAILABLE,
        real_web=True,
    ).run()
    deterministic = {
        str(record["lote_id"]): str(record["status_operacional"])
        for record in result.consolidation_result["payload"]["records"]
    }

    assert result.ml_result["status"] == "PARTIALLY_COMPLETED"
    assert result.ml_result["motivo_fallback"] == "indisponibilidade"
    assert result.ml_result["payload"]["fallback_items"] >= 1
    assert all(
        record["resultado_deterministico"] == deterministic[record["lote_id"]]
        for record in result.ml_result["payload"]["records"]
    )
    assert result.report_result.paths.pdf.stat().st_size > 0
    assert result.report_result.paths.summary.is_file()
    _write_evidence(capstone_evidence_dir, result.evidence())


def test_capstone_timeout_e_cancelamento_sao_distintos_e_limitados(
    tmp_path: Path,
    capstone_evidence_dir: Path,
) -> None:
    timeout = LocalCapstonePipeline(
        tmp_path / "timeout",
        CrisisScenario.DEPENDENCY_TIMEOUT,
    ).run()
    canceled = LocalCapstonePipeline(
        tmp_path / "canceled",
        CrisisScenario.DEPENDENCY_CANCELED,
    ).run()

    assert "TIMEOUT" in timeout.dependency_states
    assert "CANCELED" in canceled.dependency_states
    assert timeout.elapsed_seconds < 2
    assert canceled.elapsed_seconds < 2
    assert timeout.report_result.snapshot.modo_degradado
    assert canceled.report_result.snapshot.modo_degradado
    assert timeout.report_result.paths.pdf.is_file()
    assert canceled.report_result.paths.pdf.is_file()
    assert all(
        state not in {"START", "RUNNING"}
        for state in {
            *timeout.local_task_states.values(),
            *canceled.local_task_states.values(),
        }
    )

    evidence = timeout.evidence()
    evidence.update(
        {
            "scenario": CrisisScenario.DEPENDENCY_FAILURE.value,
            "sabotage": CrisisScenario.DEPENDENCY_FAILURE.value,
            "dependency_states": ["TIMEOUT", "CANCELED"],
            "observed_states": {
                "timeout": timeout.local_task_states,
                "canceled": canceled.local_task_states,
            },
            "processed_count": (
                timeout.report_result.snapshot.processed_items
                + canceled.report_result.snapshot.processed_items
            ),
            "fallback": "continuidade_degradada_por_dependencia",
            "terminal_count": len(timeout.gateway.tasks) + len(canceled.gateway.tasks),
            "artifacts": sorted(
                {*timeout.artifact_names, *canceled.artifact_names}
            ),
            "identifiers": {
                **timeout.evidence()["identifiers"],
                "related_executions": [
                    timeout.evidence()["identifiers"],
                    canceled.evidence()["identifiers"],
                ],
            },
            "elapsed_ms": round(
                (timeout.elapsed_seconds + canceled.elapsed_seconds) * 1000
            ),
        }
    )
    _write_evidence(capstone_evidence_dir, evidence)


@pytest.mark.browser
def test_capstone_telegram_falha_para_email_e_depois_log_local(
    tmp_path: Path,
    capstone_evidence_dir: Path,
) -> None:
    result = LocalCapstonePipeline(
        tmp_path / "notification-fallback",
        CrisisScenario.NOTIFICATION_FAILURE,
        real_web=True,
    ).run()
    notifications = result.report_result.notification_results
    log_content = (result.output_dir / "logs" / "pipeline.jsonl").read_text(
        encoding="utf-8"
    )

    assert len(notifications) == 2
    assert notifications[0].entregues == ("email",)
    assert notifications[0].falhos == ("telegram",)
    assert notifications[1].entregues == ("log_local",)
    assert notifications[1].falhos == ("telegram", "email")
    assert "ALERTA LOCAL: perda de canal externo" in log_content
    assert result.report_result.paths.summary.is_file()
    _write_evidence(capstone_evidence_dir, result.evidence())


@dataclass
class _AlertSpy:
    events: list[str]

    def notificar(self, alert: object) -> ResultadoEntrega:
        self.events.append(str(getattr(alert, "evento", "")))
        return ResultadoEntrega(("email",), ())


def _coordinator(
    database: Path,
    orchestrator: str,
) -> CoexistenceCoordinator:
    settings = MigrationControlSettings(
        database,
        orchestrator,
        "smart_office",
        lease_ttl_seconds=30,
        desktop_session_id="runner-local-crise",
    )
    return CoexistenceCoordinator(SQLiteLeaseStore(database), settings)


@pytest.mark.browser
def test_capstone_official_shadow_nao_duplica_relatorio_ou_alerta(
    tmp_path: Path,
    capstone_evidence_dir: Path,
) -> None:
    database = tmp_path / "coexistence.sqlite3"
    official = _coordinator(database, "smart_office")
    shadow = _coordinator(database, "maestro")
    concurrency_execution_id = (
        f"local-exec-{CrisisScenario.CONCURRENCY.value}"
    )
    official_permit = official.begin_execution(
        concurrency_execution_id,
        owner_id="local-official",
    )
    shadow_permit = shadow.begin_execution(
        concurrency_execution_id,
        owner_id="local-shadow",
    )
    pipeline = LocalCapstonePipeline(
        tmp_path / "pipeline",
        CrisisScenario.CONCURRENCY,
        real_web=True,
        report_coexistence=official,
        report_migration_permit=official_permit,
    ).run()
    payload = pipeline.reporting_payload()
    first = pipeline.report_result
    duplicate_alerts = _AlertSpy([])
    shadow_alerts = _AlertSpy([])
    official_service = CapstoneReportService(
        pipeline.output_dir / "reports",
        alerts=duplicate_alerts,
        coexistence=official,
        migration_permit=official_permit,
    )
    report_mtime = first.paths.pdf.stat().st_mtime_ns
    shadow_result = CapstoneReportService(
        tmp_path / "shadow-reports",
        alerts=shadow_alerts,
        coexistence=shadow,
        migration_permit=shadow_permit,
    ).generate(payload)
    duplicate = official_service.generate(payload)
    publication_count = sum(
        result.published for result in (first, shadow_result, duplicate)
    )
    duplicate_count = max(0, publication_count - 1)

    assert first.published
    assert first.publication_reason == "official"
    assert not shadow_result.published
    assert shadow_result.publication_reason == "shadow_mode"
    assert not (tmp_path / "shadow-reports").exists()
    assert not duplicate.published
    assert duplicate.publication_reason == "already_completed"
    assert duplicate.paths.pdf.stat().st_mtime_ns == report_mtime
    assert publication_count == 1
    assert len(first.notification_results) == 1
    assert first.notification_results[0].evento == "ml_indisponivel"
    assert not duplicate_alerts.events
    assert not shadow_alerts.events

    evidence = pipeline.evidence(duplicates=duplicate_count)
    evidence.update(
        {
            "alerts": [item.to_dict() for item in first.notification_results],
            "artifacts": [
                first.paths.summary.name,
                first.paths.markdown.name,
                first.paths.pdf.name,
                first.paths.excel.name,
            ],
            "publication": {
                "official": first.publication_reason,
                "shadow": shadow_result.publication_reason,
                "duplicate": duplicate.publication_reason,
            },
        }
    )
    _write_evidence(capstone_evidence_dir, evidence)


@pytest.mark.browser
def test_capstone_dado_irrecuperavel_gera_uma_dead_letter_e_continua(
    tmp_path: Path,
    capstone_evidence_dir: Path,
) -> None:
    result = LocalCapstonePipeline(
        tmp_path / "dead-letter",
        CrisisScenario.IRRECOVERABLE_DATA,
        real_web=True,
    ).run()
    dead_letter = result.dead_letter_path
    record = json.loads(dead_letter.read_text(encoding="utf-8"))
    validations = json.loads(
        (result.output_dir / "data" / "validations.json").read_text(
            encoding="utf-8"
        )
    )

    assert result.reference_attempts == 6
    assert result.dead_letter_count == 1
    assert record["tentativas"] == 3
    assert len(validations) == 3
    assert result.report_result.snapshot.processed_items == 4
    assert result.report_result.snapshot.dead_letter_produced
    assert result.report_result.paths.pdf.is_file()
    assert result.report_result.notification_results[0].evento == (
        "dead_letter_produzido"
    )
    assert "observacao" not in record["item"]
    assert all(
        state not in {"START", "RUNNING"}
        for state in result.local_task_states.values()
    )
    _write_evidence(capstone_evidence_dir, result.evidence())
