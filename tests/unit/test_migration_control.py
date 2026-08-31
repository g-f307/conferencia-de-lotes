from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.migration_control import (
    CoexistenceCoordinator,
    DesktopSessionBusyError,
    DuplicateExecutionError,
    LeaseOwnershipError,
    MigrationControlSettings,
    PublicationMode,
    SQLiteLeaseStore,
    build_idempotency_key,
)

pytestmark = pytest.mark.unit


@dataclass
class _Clock:
    current: datetime = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def _coordinator(
    database: Path,
    clock: _Clock,
    *,
    orchestrator: str,
    official_publisher: str = "smart_office",
    ttl: float = 30,
) -> CoexistenceCoordinator:
    settings = MigrationControlSettings(
        database,
        orchestrator,
        official_publisher,
        lease_ttl_seconds=ttl,
        desktop_session_id="runner-01",
    )
    return CoexistenceCoordinator(SQLiteLeaseStore(database, now=clock), settings)


def test_idempotency_key_e_estavel_e_nao_expoe_referencia() -> None:
    first = build_idempotency_key("pedido-confidencial-001")
    second = build_idempotency_key("pedido-confidencial-001")

    assert first == second
    assert first.startswith("capstone-v1-")
    assert "pedido-confidencial" not in first


def test_lease_de_execucao_tem_apenas_um_proprietario_ativo(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    database = tmp_path / "leases.sqlite3"
    smart = _coordinator(database, clock, orchestrator="smart_office")
    split_brain_maestro = _coordinator(
        database,
        clock,
        orchestrator="maestro",
        official_publisher="maestro",
    )

    permit = smart.begin_execution("exec-116", owner_id="smart-task")
    with pytest.raises(DuplicateExecutionError, match="proprietário ativo"):
        split_brain_maestro.begin_execution("exec-116", owner_id="maestro-task")

    events = smart.store.events(permit.idempotency_key)
    assert events[-1]["event_type"] == "LEASE_REJECTED_DUPLICATE"
    assert events[-1]["owner_id"] == "maestro-task"


def test_lease_heartbeat_estende_validade_e_impede_takeover(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    database = tmp_path / "leases.sqlite3"
    owner = _coordinator(database, clock, orchestrator="smart_office", ttl=10)
    contender = _coordinator(
        database,
        clock,
        orchestrator="maestro",
        official_publisher="maestro",
        ttl=10,
    )
    permit = owner.begin_execution("exec-heartbeat", owner_id="owner")
    original_expiration = permit.expires_at

    clock.advance(8)
    renewed = owner.heartbeat(permit)

    assert renewed.expires_at is not None
    assert original_expiration is not None
    assert renewed.expires_at > original_expiration
    clock.advance(5)
    with pytest.raises(DuplicateExecutionError):
        contender.begin_execution("exec-heartbeat", owner_id="contender")


def test_lease_expirada_e_recuperada_com_novo_fencing_token(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    database = tmp_path / "leases.sqlite3"
    first = _coordinator(database, clock, orchestrator="smart_office", ttl=5)
    second = _coordinator(
        database,
        clock,
        orchestrator="maestro",
        official_publisher="maestro",
        ttl=5,
    )
    stale = first.begin_execution("exec-recovery", owner_id="owner-old")

    clock.advance(6)
    recovered = second.begin_execution("exec-recovery", owner_id="owner-new")

    assert recovered.fencing_token == 2
    with pytest.raises(LeaseOwnershipError, match="lease válida"):
        first.run_effect_once(stale, "report", lambda: None)
    assert second.run_effect_once(recovered, "report", lambda: "ok").value == "ok"


def test_shadow_compara_sem_publicar_efeitos_oficiais(tmp_path: Path) -> None:
    clock = _Clock()
    database = tmp_path / "leases.sqlite3"
    official = _coordinator(database, clock, orchestrator="smart_office")
    shadow = _coordinator(database, clock, orchestrator="maestro")
    official_permit = official.begin_execution("exec-shadow", owner_id="smart")
    shadow_permit = shadow.begin_execution("exec-shadow", owner_id="maestro")
    calls: list[str] = []

    shadow_result = shadow.run_effect_once(
        shadow_permit,
        "official_write",
        lambda: calls.append("shadow"),
    )
    official_result = official.run_effect_once(
        official_permit,
        "official_write",
        lambda: calls.append("official"),
    )

    assert shadow_permit.publication_mode is PublicationMode.SHADOW
    assert not shadow_result.executed
    assert shadow_result.reason == "shadow_mode"
    assert official_result.executed
    assert calls == ["official"]


def test_idempotent_effect_executa_uma_vez_e_falha_pode_ser_retentada(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    coordinator = _coordinator(
        tmp_path / "leases.sqlite3", clock, orchestrator="smart_office"
    )
    permit = coordinator.begin_execution("exec-effects", owner_id="owner")
    calls: list[str] = []

    first = coordinator.run_effect_once(
        permit, "notification", lambda: calls.append("sent")
    )
    duplicate = coordinator.run_effect_once(
        permit, "notification", lambda: calls.append("duplicated")
    )

    def fail() -> None:
        raise RuntimeError("falha controlada")

    with pytest.raises(RuntimeError, match="controlada"):
        coordinator.run_effect_once(permit, "write", fail)
    retry = coordinator.run_effect_once(permit, "write", lambda: "persisted")

    assert first.executed
    assert not duplicate.executed
    assert duplicate.reason == "already_completed"
    assert calls == ["sent"]
    assert retry.executed
    assert retry.value == "persisted"


def test_lease_da_sessao_desktop_e_exclusiva_e_recuperavel(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    database = tmp_path / "leases.sqlite3"
    smart = _coordinator(database, clock, orchestrator="smart_office", ttl=5)
    maestro = _coordinator(database, clock, orchestrator="maestro", ttl=5)
    smart_permit = smart.begin_execution("exec-smart", owner_id="smart")
    maestro_permit = maestro.begin_execution("exec-maestro", owner_id="maestro")

    with (
        smart.desktop_session(smart_permit),
        pytest.raises(DesktopSessionBusyError, match="sessão gráfica"),
        maestro.desktop_session(maestro_permit),
    ):
        pass

    with maestro.desktop_session(maestro_permit) as recovered:
        assert recovered.record.owner_id == "maestro"


def test_lease_keepalive_impede_takeover_durante_efeito_maior_que_ttl(
    tmp_path: Path,
) -> None:
    database = tmp_path / "leases.sqlite3"
    owner = CoexistenceCoordinator(
        SQLiteLeaseStore(database),
        MigrationControlSettings(
            database,
            "smart_office",
            "smart_office",
            lease_ttl_seconds=0.15,
        ),
    )
    contender = CoexistenceCoordinator(
        SQLiteLeaseStore(database),
        MigrationControlSettings(
            database,
            "maestro",
            "maestro",
            lease_ttl_seconds=0.15,
        ),
    )
    permit = owner.begin_execution("exec-long-effect", owner_id="owner")

    def long_effect() -> str:
        time.sleep(0.3)
        with pytest.raises(DuplicateExecutionError):
            contender.begin_execution("exec-long-effect", owner_id="contender")
        return "completed"

    result = owner.run_effect_once(permit, "report", long_effect)

    assert result.executed
    assert result.value == "completed"


def test_lease_keepalive_mantem_sessao_desktop_apos_ttl(tmp_path: Path) -> None:
    database = tmp_path / "leases.sqlite3"
    official = CoexistenceCoordinator(
        SQLiteLeaseStore(database),
        MigrationControlSettings(
            database,
            "smart_office",
            "smart_office",
            lease_ttl_seconds=0.15,
            desktop_session_id="shared",
        ),
    )
    shadow = CoexistenceCoordinator(
        SQLiteLeaseStore(database),
        MigrationControlSettings(
            database,
            "maestro",
            "smart_office",
            lease_ttl_seconds=0.15,
            desktop_session_id="shared",
        ),
    )
    split_brain = CoexistenceCoordinator(
        SQLiteLeaseStore(database),
        MigrationControlSettings(
            database,
            "maestro",
            "maestro",
            lease_ttl_seconds=0.15,
            desktop_session_id="shared",
        ),
    )
    official_permit = official.begin_execution("exec-official", owner_id="official")
    shadow_permit = shadow.begin_execution("exec-shadow", owner_id="shadow")

    with official.desktop_session(official_permit):
        time.sleep(0.3)
        with pytest.raises(DuplicateExecutionError):
            split_brain.begin_execution("exec-official", owner_id="contender")
        with (
            pytest.raises(DesktopSessionBusyError),
            shadow.desktop_session(shadow_permit),
        ):
            pass


def test_lease_mesmo_owner_nao_renova_desktop_de_outra_execucao(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    coordinator = _coordinator(
        tmp_path / "leases.sqlite3",
        clock,
        orchestrator="smart_office",
    )
    first = coordinator.begin_execution("exec-a", owner_id="shared-owner")
    second = coordinator.begin_execution("exec-b", owner_id="shared-owner")

    with (
        coordinator.desktop_session(first),
        pytest.raises(DesktopSessionBusyError),
        coordinator.desktop_session(second),
    ):
        pass
