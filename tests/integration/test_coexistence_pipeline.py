from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

import src.capstone_reporting.service as report_service
from src.capstone_orchestrator import (
    CapstoneOrchestrationSettings,
    CapstoneOrchestrator,
    CapstoneStage,
)
from src.capstone_reporting import CapstoneReportService
from src.capstone_reporting.main import CapstoneReportSettings, run
from src.maestro_client import InMemoryMaestroGateway
from src.migration_control import (
    CoexistenceCoordinator,
    DesktopSessionBusyError,
    MigrationControlSettings,
    SQLiteLeaseStore,
)
from src.orchestrator import StageResult

pytestmark = pytest.mark.integration


def _settings() -> CapstoneOrchestrationSettings:
    return CapstoneOrchestrationSettings(
        desktop_priority=90,
        default_priority=40,
        dependency_timeout_seconds=10,
        poll_interval_seconds=0.01,
    )


def _coordinator(
    database: Path,
    orchestrator: str,
) -> CoexistenceCoordinator:
    settings = MigrationControlSettings(
        database,
        orchestrator,
        "smart_office",
        lease_ttl_seconds=30,
        desktop_session_id="runner-shared",
    )
    return CoexistenceCoordinator(SQLiteLeaseStore(database), settings)


def _incident_payload() -> dict[str, object]:
    return {
        "report_type": "OPERATIONAL_INCIDENT",
        "task_id": "task-report-116",
        "source_statuses": {
            "estoque-desktop-v1": "UNAVAILABLE",
            "fornecedores-web-v1": "DEGRADED",
        },
        "consolidation_result": {
            "status": "FAILED",
            "snapshot_type": "OPERATIONAL_FAILURE",
            "execution_id": "exec-coexist-report",
            "correlation_id": "corr-coexist-report",
            "root_task_id": "root-coexist-report",
            "expected_items": 2,
            "processed_items": 0,
            "failed_items": 2,
            "review_items": 2,
            "modo_degradado": True,
            "motivo_fallback": "consolidation_timeout",
            "failure_code": "consolidation_timeout",
            "payload": {},
        },
        "ml_result": {"status": "FAILED", "payload": {"ml_decisions": []}},
    }


@dataclass(frozen=True)
class _Delivery:
    entregues: tuple[str, ...] = ("email",)
    falhos: tuple[str, ...] = ()


class _AlertSpy:
    def __init__(self) -> None:
        self.events: list[str] = []

    def notificar(self, alert) -> _Delivery:
        self.events.append(alert.evento)
        return _Delivery()


def test_coexistencia_propaga_modo_e_impede_disputa_pelo_desktop(
    tmp_path: Path,
) -> None:
    database = tmp_path / "migration.sqlite3"
    smart_control = _coordinator(database, "smart_office")
    maestro_control = _coordinator(database, "maestro")
    smart_gateway = InMemoryMaestroGateway("smart-root")
    maestro_gateway = InMemoryMaestroGateway("maestro-root")
    smart = CapstoneOrchestrator(
        smart_gateway,
        settings=_settings(),
        coexistence=smart_control,
    )
    maestro = CapstoneOrchestrator(
        maestro_gateway,
        settings=_settings(),
        coexistence=maestro_control,
    )

    smart_manifest = smart.schedule(execution_id="business-116")
    maestro_manifest = maestro.schedule(execution_id="business-116")

    assert smart_manifest.migration_permit is not None
    assert smart_manifest.migration_permit.can_publish
    assert maestro_manifest.migration_permit is not None
    assert not maestro_manifest.migration_permit.can_publish
    smart_task = smart_gateway.get_task(
        smart_manifest.task_ids[CapstoneStage.DESKTOP]
    )
    maestro_task_id = maestro_manifest.task_ids[CapstoneStage.DESKTOP]
    maestro_task = maestro_gateway.get_task(maestro_task_id)
    assert smart_task.parameters["migration_control"]["publication_mode"] == "official"
    assert maestro_task.parameters["migration_control"]["publication_mode"] == "shadow"

    maestro_gateway.activate_task(maestro_task_id)
    with (
        smart_control.desktop_session(smart_manifest.migration_permit),
        pytest.raises(DesktopSessionBusyError),
    ):
        maestro.execute_current(
            CapstoneStage.DESKTOP,
            lambda context: StageResult("SUCCESS", "não deveria executar"),
        )

    outcome = maestro.execute_current(
        CapstoneStage.DESKTOP,
        lambda context: StageResult("SUCCESS", "comparação shadow concluída"),
    )
    assert outcome.result.status == "SUCCESS"
    assert outcome.context.migration_permit is not None
    assert not outcome.context.migration_permit.can_publish

    published: list[str] = []
    smart_gateway.activate_task(smart_manifest.task_ids[CapstoneStage.WEB])
    smart.execute_current(
        CapstoneStage.WEB,
        lambda context: StageResult("SUCCESS", "cálculo official"),
        publisher=lambda context, result: published.append("official"),
    )
    maestro_gateway.activate_task(maestro_manifest.task_ids[CapstoneStage.WEB])
    maestro.execute_current(
        CapstoneStage.WEB,
        lambda context: StageResult("SUCCESS", "comparação shadow"),
        publisher=lambda context, result: published.append("shadow"),
    )
    assert published == ["official"]


def test_coexistencia_exige_identificador_compartilhado(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path / "migration.sqlite3", "smart_office")
    orchestrator = CapstoneOrchestrator(
        InMemoryMaestroGateway("smart-root"),
        settings=_settings(),
        coexistence=coordinator,
    )

    with pytest.raises(ValueError, match="execution_id compartilhado"):
        orchestrator.schedule()


def test_coexistencia_nao_duplica_relatorio_nem_alertas(tmp_path: Path) -> None:
    database = tmp_path / "migration.sqlite3"
    coordinator = _coordinator(database, "smart_office")
    permit = coordinator.begin_execution(
        "exec-coexist-report",
        owner_id="root-coexist-report",
    )
    alerts = _AlertSpy()
    output = tmp_path / "reports"
    service = CapstoneReportService(
        output,
        alerts=alerts,
        coexistence=coordinator,
        migration_permit=permit,
    )

    first = service.generate(_incident_payload())
    first_mtime = first.paths.pdf.stat().st_mtime_ns
    delivered_events = tuple(alerts.events)
    duplicate = service.generate(_incident_payload())

    assert first.published
    assert first.publication_reason == "official"
    assert not duplicate.published
    assert duplicate.publication_reason == "already_completed"
    assert duplicate.paths.pdf.stat().st_mtime_ns == first_mtime
    assert tuple(alerts.events) == delivered_events
    assert all(
        attempt.status == "SKIPPED_DUPLICATE"
        for attempt in duplicate.notification_results
    )


def test_coexistencia_shadow_valida_snapshot_sem_gravar_ou_notificar(
    tmp_path: Path,
) -> None:
    database = tmp_path / "migration.sqlite3"
    shadow = _coordinator(database, "maestro")
    permit = shadow.begin_execution(
        "exec-coexist-report",
        owner_id="maestro-shadow",
    )
    alerts = _AlertSpy()
    output = tmp_path / "shadow-reports"

    result = CapstoneReportService(
        output,
        alerts=alerts,
        coexistence=shadow,
        migration_permit=permit,
    ).generate(_incident_payload())

    assert result.snapshot.execution_id == "exec-coexist-report"
    assert not result.published
    assert result.publication_reason == "shadow_mode"
    assert alerts.events == []
    assert not output.exists()


def test_coexistencia_entrypoint_extrai_ids_do_envelope_e_bloqueia_repeticao(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "pipeline.json"
    input_path.write_text(
        json.dumps(_incident_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "reports"
    database = tmp_path / "migration.sqlite3"
    monkeypatch.setenv("MIGRATION_CONTROL_ENABLED", "true")
    monkeypatch.setenv("MIGRATION_LEASE_DB_PATH", str(database))
    monkeypatch.setenv("MIGRATION_ORCHESTRATOR", "smart_office")
    monkeypatch.setenv("MIGRATION_OFFICIAL_PUBLISHER", "smart_office")
    monkeypatch.setenv("ALERTS_ENABLED", "false")
    monkeypatch.setenv("MAESTRO_ENABLED", "false")
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "false")
    monkeypatch.setenv("WEB_AUTOMATION_ENABLED", "false")
    monkeypatch.setenv("ML_ENABLED", "false")
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "execucao.log"))
    settings = CapstoneReportSettings(input_path, output, 300)

    first = run(settings)
    duplicate = run(settings)

    assert first["execution_id"] == "exec-coexist-report"
    assert first["published"] is True
    assert duplicate["published"] is False
    assert duplicate["publication_reason"] == "already_completed"


def test_coexistencia_retomada_nao_repete_alerta_ja_entregue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "migration.sqlite3"
    coordinator = _coordinator(database, "smart_office")
    permit = coordinator.begin_execution(
        "exec-coexist-report",
        owner_id="root-coexist-report",
    )
    alerts = _AlertSpy()
    output = tmp_path / "reports"
    original_write = report_service._write_json_atomic
    summary_attempts = 0

    def fail_first_summary(destination: Path, payload) -> None:
        nonlocal summary_attempts
        summary_attempts += 1
        if summary_attempts == 1:
            raise OSError("falha controlada após notificações")
        original_write(destination, payload)

    monkeypatch.setattr(report_service, "_write_json_atomic", fail_first_summary)
    service = CapstoneReportService(
        output,
        alerts=alerts,
        coexistence=coordinator,
        migration_permit=permit,
    )

    with pytest.raises(OSError, match="após notificações"):
        service.generate(_incident_payload())
    delivered_once = tuple(alerts.events)

    resumed = service.generate(_incident_payload())

    assert resumed.published
    assert resumed.publication_reason == "resumed"
    assert tuple(alerts.events) == delivered_once
    assert resumed.paths.summary.is_file()
