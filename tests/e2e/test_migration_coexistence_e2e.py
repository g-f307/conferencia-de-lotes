from __future__ import annotations

from pathlib import Path

import pytest

from src.migration_control import (
    CoexistenceCoordinator,
    MigrationControlSettings,
    SQLiteLeaseStore,
)

pytestmark = pytest.mark.e2e


def _coordinator(database: Path, orchestrator: str) -> CoexistenceCoordinator:
    settings = MigrationControlSettings(
        database,
        orchestrator,
        "smart_office",
        lease_ttl_seconds=30,
        desktop_session_id="e2e-session",
    )
    return CoexistenceCoordinator(SQLiteLeaseStore(database), settings)


def test_duplicate_effects_are_blocked_during_orchestrator_coexistence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "migration.sqlite3"
    official = _coordinator(database, "smart_office")
    shadow = _coordinator(database, "maestro")
    official_permit = official.begin_execution("exec-e2e-116", owner_id="smart")
    shadow_permit = shadow.begin_execution("exec-e2e-116", owner_id="maestro")
    effects: list[str] = []

    for effect in ("business_write", "report", "notification"):
        shadow_result = shadow.run_effect_once(
            shadow_permit,
            effect,
            lambda current=effect: effects.append(f"shadow:{current}"),
        )
        official_result = official.run_effect_once(
            official_permit,
            effect,
            lambda current=effect: effects.append(f"official:{current}"),
        )
        duplicate = official.run_effect_once(
            official_permit,
            effect,
            lambda current=effect: effects.append(f"duplicate:{current}"),
        )
        assert not shadow_result.executed
        assert official_result.executed
        assert not duplicate.executed

    assert effects == [
        "official:business_write",
        "official:report",
        "official:notification",
    ]
