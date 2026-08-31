"""Controle local de coexistência entre orquestradores durante a migração."""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Generic, TypeVar

from src.logging_config import LOGGER_NAME

LOGGER = logging.getLogger(LOGGER_NAME)
T = TypeVar("T")

SUPPORTED_ORCHESTRATORS = frozenset({"maestro", "smart_office"})


class PublicationMode(str, Enum):
    OFFICIAL = "official"
    SHADOW = "shadow"


class DuplicateExecutionError(RuntimeError):
    """A execução oficial já pertence a outro processo."""


class LeaseOwnershipError(RuntimeError):
    """O processo não possui mais uma lease válida."""


class DesktopSessionBusyError(RuntimeError):
    """A sessão gráfica está ocupada por outra execução."""


@dataclass(frozen=True)
class MigrationControlSettings:
    database_path: Path
    orchestrator: str
    official_publisher: str
    lease_ttl_seconds: float = 300.0
    desktop_session_id: str = "default"

    def __post_init__(self) -> None:
        _orchestrator(self.orchestrator, "orchestrator")
        _orchestrator(self.official_publisher, "official_publisher")
        if self.lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds deve ser maior que zero")
        _required_text(self.desktop_session_id, "desktop_session_id")

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> MigrationControlSettings:
        root = (base_dir or Path.cwd()).resolve()
        configured_path = Path(
            os.getenv(
                "MIGRATION_LEASE_DB_PATH",
                "data/output/migration_leases.sqlite3",
            )
        ).expanduser()
        database_path = (
            configured_path
            if configured_path.is_absolute()
            else (root / configured_path).resolve()
        )
        return cls(
            database_path=database_path,
            orchestrator=os.getenv("MIGRATION_ORCHESTRATOR", "smart_office"),
            official_publisher=os.getenv(
                "MIGRATION_OFFICIAL_PUBLISHER", "smart_office"
            ),
            lease_ttl_seconds=float(os.getenv("MIGRATION_LEASE_TTL_SECONDS", "300")),
            desktop_session_id=os.getenv("MIGRATION_DESKTOP_SESSION_ID", "default"),
        )

    @property
    def publication_mode(self) -> PublicationMode:
        if self.orchestrator.strip().casefold() == self.official_publisher.strip().casefold():
            return PublicationMode.OFFICIAL
        return PublicationMode.SHADOW


@dataclass(frozen=True)
class LeaseRecord:
    resource_key: str
    idempotency_key: str
    requesting_orchestrator: str
    owner_id: str
    acquired_at: datetime
    expires_at: datetime
    heartbeat_at: datetime
    publication_mode: PublicationMode
    fencing_token: int


@dataclass(frozen=True)
class ExecutionPermit:
    idempotency_key: str
    requesting_orchestrator: str
    owner_id: str
    publication_mode: PublicationMode
    fencing_token: int | None
    expires_at: datetime | None

    @property
    def can_publish(self) -> bool:
        return (
            self.publication_mode is PublicationMode.OFFICIAL
            and self.fencing_token is not None
        )


@dataclass(frozen=True)
class EffectResult(Generic[T]):
    executed: bool
    value: T | None = None
    reason: str = ""


@dataclass(frozen=True)
class DesktopLease:
    coordinator: CoexistenceCoordinator
    permit: ExecutionPermit
    record: LeaseRecord

    def heartbeat(self) -> LeaseRecord:
        return self.coordinator._renew_resource(self.record)


@dataclass(frozen=True)
class _LeaseAttempt:
    acquired: bool
    record: LeaseRecord
    recovered: bool = False


class _Keepalive:
    """Renova recursos durante callbacks potencialmente longos."""

    def __init__(
        self,
        renew: Callable[[], None],
        ttl_seconds: float,
    ) -> None:
        self.renew = renew
        self.interval = max(0.05, min(ttl_seconds / 3, 30.0))
        self.stopped = threading.Event()
        self.failure: BaseException | None = None
        self.thread = threading.Thread(
            target=self._run,
            name="migration-lease-keepalive",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()
        self.thread.join()
        if self.failure is not None:
            raise LeaseOwnershipError("falha ao renovar lease durante a operação") from self.failure

    def _run(self) -> None:
        while not self.stopped.wait(self.interval):
            try:
                self.renew()
            except BaseException as exc:  # noqa: BLE001 -- propagated to owner thread
                self.failure = exc
                self.stopped.set()
                return


class SQLiteLeaseStore:
    """Persistência transacional de leases, efeitos e auditoria."""

    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.path = Path(path)
        self.now = now
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def acquire(
        self,
        *,
        resource_key: str,
        idempotency_key: str,
        requesting_orchestrator: str,
        owner_id: str,
        publication_mode: PublicationMode,
        ttl_seconds: float,
    ) -> _LeaseAttempt:
        now = self._now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM migration_leases WHERE resource_key = ?",
                (resource_key,),
            ).fetchone()
            if row is None:
                record = LeaseRecord(
                    resource_key,
                    idempotency_key,
                    requesting_orchestrator,
                    owner_id,
                    now,
                    expires_at,
                    now,
                    publication_mode,
                    1,
                )
                self._insert_lease(connection, record)
                self._event(connection, record, "LEASE_ACQUIRED")
                connection.commit()
                return _LeaseAttempt(True, record)

            current = self._record(row)
            if (
                current.owner_id == owner_id
                and current.idempotency_key == idempotency_key
                and current.expires_at > now
            ):
                record = self._replace_lease_times(current, expires_at, now)
                self._update_lease(connection, record)
                self._event(connection, record, "LEASE_RENEWED")
                connection.commit()
                return _LeaseAttempt(True, record)

            if current.expires_at <= now:
                record = LeaseRecord(
                    resource_key,
                    idempotency_key,
                    requesting_orchestrator,
                    owner_id,
                    now,
                    expires_at,
                    now,
                    publication_mode,
                    current.fencing_token + 1,
                )
                self._update_lease(connection, record)
                self._event(connection, record, "LEASE_RECOVERED")
                connection.commit()
                return _LeaseAttempt(True, record, recovered=True)

            self._event(
                connection,
                current,
                "LEASE_REJECTED_DUPLICATE",
                requester=requesting_orchestrator,
                requester_owner=owner_id,
            )
            connection.commit()
            return _LeaseAttempt(False, current)

    def renew(self, record: LeaseRecord, ttl_seconds: float) -> LeaseRecord:
        now = self._now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._select_lease(connection, record.resource_key)
            if not self._same_active_owner(current, record, now):
                connection.rollback()
                raise LeaseOwnershipError(
                    f"lease perdida para resource_key={record.resource_key}"
                )
            renewed = self._replace_lease_times(current, expires_at, now)
            self._update_lease(connection, renewed)
            self._event(connection, renewed, "HEARTBEAT")
            connection.commit()
            return renewed

    def release(self, record: LeaseRecord) -> bool:
        now = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._select_lease(connection, record.resource_key)
            if current is None or not self._same_owner(current, record):
                connection.rollback()
                return False
            released = self._replace_lease_times(current, now, now)
            self._update_lease(connection, released)
            self._event(connection, released, "LEASE_RELEASED")
            connection.commit()
            return True

    def record_shadow(self, permit: ExecutionPermit) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._event_values(
                connection,
                resource_key=f"execution:{permit.idempotency_key}",
                idempotency_key=permit.idempotency_key,
                event_type="SHADOW_STARTED",
                requesting_orchestrator=permit.requesting_orchestrator,
                owner_id=permit.owner_id,
                publication_mode=permit.publication_mode,
                fencing_token=None,
            )
            connection.commit()

    def claim_effect(
        self,
        permit: ExecutionPermit,
        effect_name: str,
        ttl_seconds: float,
    ) -> tuple[bool, str]:
        now = self._now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        resource_key = f"execution:{permit.idempotency_key}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            lease = self._select_lease(connection, resource_key)
            if not self._permit_owns(lease, permit, now):
                connection.rollback()
                raise LeaseOwnershipError(
                    "execução oficial não possui lease válida para publicar"
                )
            row = connection.execute(
                """
                SELECT status, expires_at FROM migration_effects
                WHERE idempotency_key = ? AND effect_name = ?
                """,
                (permit.idempotency_key, effect_name),
            ).fetchone()
            if row is not None:
                status = str(row["status"])
                claim_expiration = _parse_time(row["expires_at"])
                if status == "COMPLETED":
                    self._effect_event(connection, permit, effect_name, "EFFECT_DUPLICATE")
                    connection.commit()
                    return False, "already_completed"
                if status == "RUNNING" and claim_expiration > now:
                    self._effect_event(connection, permit, effect_name, "EFFECT_BUSY")
                    connection.commit()
                    return False, "already_running"

            connection.execute(
                """
                INSERT INTO migration_effects (
                    idempotency_key, effect_name, owner_id, fencing_token,
                    status, claimed_at, expires_at, completed_at
                ) VALUES (?, ?, ?, ?, 'RUNNING', ?, ?, NULL)
                ON CONFLICT(idempotency_key, effect_name) DO UPDATE SET
                    owner_id=excluded.owner_id,
                    fencing_token=excluded.fencing_token,
                    status='RUNNING',
                    claimed_at=excluded.claimed_at,
                    expires_at=excluded.expires_at,
                    completed_at=NULL
                """,
                (
                    permit.idempotency_key,
                    effect_name,
                    permit.owner_id,
                    permit.fencing_token,
                    _format_time(now),
                    _format_time(expires_at),
                ),
            )
            self._effect_event(connection, permit, effect_name, "EFFECT_CLAIMED")
            connection.commit()
            return True, "claimed"

    def complete_effect(self, permit: ExecutionPermit, effect_name: str) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE migration_effects
                SET status='COMPLETED', completed_at=?, expires_at=?
                WHERE idempotency_key=? AND effect_name=? AND owner_id=?
                    AND fencing_token=? AND status='RUNNING'
                """,
                (
                    _format_time(now),
                    _format_time(now),
                    permit.idempotency_key,
                    effect_name,
                    permit.owner_id,
                    permit.fencing_token,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise LeaseOwnershipError(
                    f"efeito {effect_name} não pertence mais à execução"
                )
            self._effect_event(connection, permit, effect_name, "EFFECT_COMPLETED")
            connection.commit()

    def renew_effect(
        self,
        permit: ExecutionPermit,
        effect_name: str,
        ttl_seconds: float,
    ) -> None:
        now = self._now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            lease = self._select_lease(
                connection,
                f"execution:{permit.idempotency_key}",
            )
            if not self._permit_owns(lease, permit, now):
                connection.rollback()
                raise LeaseOwnershipError("lease de execução perdida durante efeito")
            cursor = connection.execute(
                """
                UPDATE migration_effects SET expires_at=?
                WHERE idempotency_key=? AND effect_name=? AND owner_id=?
                    AND fencing_token=? AND status='RUNNING'
                """,
                (
                    _format_time(expires_at),
                    permit.idempotency_key,
                    effect_name,
                    permit.owner_id,
                    permit.fencing_token,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise LeaseOwnershipError(
                    f"efeito {effect_name} não pertence mais à execução"
                )
            connection.commit()

    def abandon_effect(self, permit: ExecutionPermit, effect_name: str) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE migration_effects
                SET status='FAILED', expires_at=?
                WHERE idempotency_key=? AND effect_name=? AND owner_id=?
                    AND fencing_token=? AND status='RUNNING'
                """,
                (
                    _format_time(now),
                    permit.idempotency_key,
                    effect_name,
                    permit.owner_id,
                    permit.fencing_token,
                ),
            )
            self._effect_event(connection, permit, effect_name, "EFFECT_FAILED")
            connection.commit()

    def events(self, idempotency_key: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_type, resource_key, requesting_orchestrator,
                    owner_id, publication_mode, fencing_token, created_at, details
                FROM migration_events
                WHERE idempotency_key=? ORDER BY id
                """,
                (idempotency_key,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS migration_leases (
                    resource_key TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL,
                    requesting_orchestrator TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    publication_mode TEXT NOT NULL,
                    fencing_token INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS migration_effects (
                    idempotency_key TEXT NOT NULL,
                    effect_name TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    fencing_token INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    completed_at TEXT,
                    PRIMARY KEY (idempotency_key, effect_name)
                );
                CREATE TABLE IF NOT EXISTS migration_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT NOT NULL,
                    resource_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    requesting_orchestrator TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    publication_mode TEXT NOT NULL,
                    fencing_token INTEGER,
                    created_at TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _select_lease(
        self, connection: sqlite3.Connection, resource_key: str
    ) -> LeaseRecord | None:
        row = connection.execute(
            "SELECT * FROM migration_leases WHERE resource_key=?",
            (resource_key,),
        ).fetchone()
        return self._record(row) if row is not None else None

    @staticmethod
    def _record(row: sqlite3.Row) -> LeaseRecord:
        return LeaseRecord(
            resource_key=str(row["resource_key"]),
            idempotency_key=str(row["idempotency_key"]),
            requesting_orchestrator=str(row["requesting_orchestrator"]),
            owner_id=str(row["owner_id"]),
            acquired_at=_parse_time(row["acquired_at"]),
            expires_at=_parse_time(row["expires_at"]),
            heartbeat_at=_parse_time(row["heartbeat_at"]),
            publication_mode=PublicationMode(row["publication_mode"]),
            fencing_token=int(row["fencing_token"]),
        )

    @staticmethod
    def _insert_lease(connection: sqlite3.Connection, record: LeaseRecord) -> None:
        connection.execute(
            """
            INSERT INTO migration_leases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            SQLiteLeaseStore._lease_values(record),
        )

    @staticmethod
    def _update_lease(connection: sqlite3.Connection, record: LeaseRecord) -> None:
        connection.execute(
            """
            UPDATE migration_leases SET
                idempotency_key=?, requesting_orchestrator=?, owner_id=?,
                acquired_at=?, expires_at=?, heartbeat_at=?,
                publication_mode=?, fencing_token=?
            WHERE resource_key=?
            """,
            (*SQLiteLeaseStore._lease_values(record)[1:], record.resource_key),
        )

    @staticmethod
    def _lease_values(record: LeaseRecord) -> tuple[object, ...]:
        return (
            record.resource_key,
            record.idempotency_key,
            record.requesting_orchestrator,
            record.owner_id,
            _format_time(record.acquired_at),
            _format_time(record.expires_at),
            _format_time(record.heartbeat_at),
            record.publication_mode.value,
            record.fencing_token,
        )

    @staticmethod
    def _replace_lease_times(
        record: LeaseRecord, expires_at: datetime, heartbeat_at: datetime
    ) -> LeaseRecord:
        return LeaseRecord(
            record.resource_key,
            record.idempotency_key,
            record.requesting_orchestrator,
            record.owner_id,
            record.acquired_at,
            expires_at,
            heartbeat_at,
            record.publication_mode,
            record.fencing_token,
        )

    @staticmethod
    def _same_owner(current: LeaseRecord, expected: LeaseRecord) -> bool:
        return (
            current.owner_id == expected.owner_id
            and current.fencing_token == expected.fencing_token
        )

    @staticmethod
    def _same_active_owner(
        current: LeaseRecord | None, expected: LeaseRecord, now: datetime
    ) -> bool:
        return (
            current is not None
            and SQLiteLeaseStore._same_owner(current, expected)
            and current.expires_at > now
        )

    @staticmethod
    def _permit_owns(
        current: LeaseRecord | None, permit: ExecutionPermit, now: datetime
    ) -> bool:
        return (
            current is not None
            and current.owner_id == permit.owner_id
            and current.fencing_token == permit.fencing_token
            and current.expires_at > now
        )

    def _event(
        self,
        connection: sqlite3.Connection,
        record: LeaseRecord,
        event_type: str,
        *,
        requester: str | None = None,
        requester_owner: str | None = None,
    ) -> None:
        self._event_values(
            connection,
            resource_key=record.resource_key,
            idempotency_key=record.idempotency_key,
            event_type=event_type,
            requesting_orchestrator=requester or record.requesting_orchestrator,
            owner_id=requester_owner or record.owner_id,
            publication_mode=record.publication_mode,
            fencing_token=record.fencing_token,
        )

    def _effect_event(
        self,
        connection: sqlite3.Connection,
        permit: ExecutionPermit,
        effect_name: str,
        event_type: str,
    ) -> None:
        self._event_values(
            connection,
            resource_key=f"effect:{effect_name}",
            idempotency_key=permit.idempotency_key,
            event_type=event_type,
            requesting_orchestrator=permit.requesting_orchestrator,
            owner_id=permit.owner_id,
            publication_mode=permit.publication_mode,
            fencing_token=permit.fencing_token,
        )

    def _event_values(
        self,
        connection: sqlite3.Connection,
        *,
        resource_key: str,
        idempotency_key: str,
        event_type: str,
        requesting_orchestrator: str,
        owner_id: str,
        publication_mode: PublicationMode,
        fencing_token: int | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO migration_events (
                idempotency_key, resource_key, event_type,
                requesting_orchestrator, owner_id, publication_mode,
                fencing_token, created_at, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')
            """,
            (
                idempotency_key,
                resource_key,
                event_type,
                requesting_orchestrator,
                owner_id,
                publication_mode.value,
                fencing_token,
                _format_time(self._now()),
            ),
        )

    def _now(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class CoexistenceCoordinator:
    """Entrega permissões e aplica exclusão sem conhecer os SDKs externos."""

    def __init__(
        self,
        store: SQLiteLeaseStore,
        settings: MigrationControlSettings,
        *,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.store = store
        self.settings = settings
        self.logger = logger

    def begin_execution(
        self,
        execution_reference: object,
        *,
        owner_id: object,
    ) -> ExecutionPermit:
        idempotency_key = build_idempotency_key(execution_reference)
        owner = _required_text(owner_id, "owner_id")
        mode = self.settings.publication_mode
        if mode is PublicationMode.SHADOW:
            permit = ExecutionPermit(
                idempotency_key,
                self.settings.orchestrator,
                owner,
                mode,
                None,
                None,
            )
            self.store.record_shadow(permit)
            self.logger.info(
                "execução shadow iniciada orchestrator=%s owner_id=%s idempotency_key=%s; efeitos oficiais bloqueados",
                permit.requesting_orchestrator,
                permit.owner_id,
                permit.idempotency_key,
            )
            return permit

        attempt = self.store.acquire(
            resource_key=f"execution:{idempotency_key}",
            idempotency_key=idempotency_key,
            requesting_orchestrator=self.settings.orchestrator,
            owner_id=owner,
            publication_mode=mode,
            ttl_seconds=self.settings.lease_ttl_seconds,
        )
        if not attempt.acquired:
            self.logger.warning(
                "execução rejeitada por duplicidade orchestrator=%s owner_id=%s idempotency_key=%s current_owner=%s expires_at=%s",
                self.settings.orchestrator,
                owner,
                idempotency_key,
                attempt.record.owner_id,
                attempt.record.expires_at.isoformat(),
            )
            raise DuplicateExecutionError(
                "execução já possui proprietário ativo: "
                f"{attempt.record.requesting_orchestrator}/{attempt.record.owner_id}"
            )
        action = "recuperada após expiração" if attempt.recovered else "adquirida"
        self.logger.info(
            "lease de execução %s orchestrator=%s owner_id=%s idempotency_key=%s fencing_token=%s expires_at=%s",
            action,
            self.settings.orchestrator,
            owner,
            idempotency_key,
            attempt.record.fencing_token,
            attempt.record.expires_at.isoformat(),
        )
        return self._permit(attempt.record)

    def heartbeat(self, permit: ExecutionPermit) -> ExecutionPermit:
        if not permit.can_publish:
            return permit
        record = self._record_from_permit(permit)
        renewed = self.store.renew(record, self.settings.lease_ttl_seconds)
        return self._permit(renewed)

    def release(self, permit: ExecutionPermit) -> bool:
        if not permit.can_publish:
            return False
        return self.store.release(self._record_from_permit(permit))

    def run_effect_once(
        self,
        permit: ExecutionPermit,
        effect_name: object,
        action: Callable[[], T],
    ) -> EffectResult[T]:
        effect = _required_text(effect_name, "effect_name")
        if not permit.can_publish:
            self.logger.info(
                "efeito oficial ignorado em shadow effect=%s orchestrator=%s idempotency_key=%s",
                effect,
                permit.requesting_orchestrator,
                permit.idempotency_key,
            )
            return EffectResult(False, reason="shadow_mode")

        claimed, reason = self.store.claim_effect(
            permit,
            effect,
            self.settings.lease_ttl_seconds,
        )
        if not claimed:
            self.logger.warning(
                "efeito rejeitado por duplicidade effect=%s orchestrator=%s idempotency_key=%s reason=%s",
                effect,
                permit.requesting_orchestrator,
                permit.idempotency_key,
                reason,
            )
            return EffectResult(False, reason=reason)
        keepalive = _Keepalive(
            lambda: self._renew_effect(permit, effect),
            self.settings.lease_ttl_seconds,
        )
        keepalive.start()
        try:
            value = action()
        except BaseException:
            try:
                keepalive.stop()
            finally:
                self.store.abandon_effect(permit, effect)
            raise
        keepalive.stop()
        self.store.complete_effect(permit, effect)
        return EffectResult(True, value=value, reason="completed")

    @contextmanager
    def desktop_session(
        self,
        permit: ExecutionPermit,
        session_id: object | None = None,
    ):
        session = _required_text(
            session_id or self.settings.desktop_session_id,
            "session_id",
        )
        attempt = self.store.acquire(
            resource_key=f"desktop:{session}",
            idempotency_key=permit.idempotency_key,
            requesting_orchestrator=permit.requesting_orchestrator,
            owner_id=permit.owner_id,
            publication_mode=permit.publication_mode,
            ttl_seconds=self.settings.lease_ttl_seconds,
        )
        if not attempt.acquired:
            self.logger.warning(
                "sessão gráfica ocupada session_id=%s owner_id=%s current_owner=%s",
                session,
                permit.owner_id,
                attempt.record.owner_id,
            )
            raise DesktopSessionBusyError(
                f"sessão gráfica {session} pertence a {attempt.record.owner_id}"
            )
        lease = DesktopLease(self, permit, attempt.record)
        current_record = attempt.record
        record_lock = threading.Lock()

        def renew_desktop() -> None:
            nonlocal current_record
            if permit.can_publish:
                self.heartbeat(permit)
            with record_lock:
                current_record = self.store.renew(
                    current_record,
                    self.settings.lease_ttl_seconds,
                )

        keepalive = _Keepalive(
            renew_desktop,
            self.settings.lease_ttl_seconds,
        )
        keepalive.start()
        try:
            yield lease
        finally:
            try:
                keepalive.stop()
            finally:
                with record_lock:
                    self.store.release(current_record)

    def _renew_resource(self, record: LeaseRecord) -> LeaseRecord:
        return self.store.renew(record, self.settings.lease_ttl_seconds)

    def _renew_effect(self, permit: ExecutionPermit, effect_name: str) -> None:
        renewed = self.heartbeat(permit)
        self.store.renew_effect(
            renewed,
            effect_name,
            self.settings.lease_ttl_seconds,
        )

    @staticmethod
    def _permit(record: LeaseRecord) -> ExecutionPermit:
        return ExecutionPermit(
            record.idempotency_key,
            record.requesting_orchestrator,
            record.owner_id,
            record.publication_mode,
            record.fencing_token,
            record.expires_at,
        )

    @staticmethod
    def _record_from_permit(permit: ExecutionPermit) -> LeaseRecord:
        if permit.fencing_token is None or permit.expires_at is None:
            raise LeaseOwnershipError("permissão shadow não possui lease oficial")
        return LeaseRecord(
            resource_key=f"execution:{permit.idempotency_key}",
            idempotency_key=permit.idempotency_key,
            requesting_orchestrator=permit.requesting_orchestrator,
            owner_id=permit.owner_id,
            acquired_at=permit.expires_at,
            expires_at=permit.expires_at,
            heartbeat_at=permit.expires_at,
            publication_mode=permit.publication_mode,
            fencing_token=permit.fencing_token,
        )


def build_idempotency_key(execution_reference: object) -> str:
    reference = _required_text(execution_reference, "execution_reference")
    digest = hashlib.sha256(
        f"capstone-execution:v1:{reference}".encode()
    ).hexdigest()
    return f"capstone-v1-{digest}"


def _orchestrator(value: object, field_name: str) -> str:
    normalized = _required_text(value, field_name).casefold()
    if normalized not in SUPPORTED_ORCHESTRATORS:
        accepted = ", ".join(sorted(SUPPORTED_ORCHESTRATORS))
        raise ValueError(f"{field_name} deve ser um de: {accepted}")
    return normalized


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} deve ser informado")
    return normalized


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


__all__ = [
    "CoexistenceCoordinator",
    "DesktopLease",
    "DesktopSessionBusyError",
    "DuplicateExecutionError",
    "EffectResult",
    "ExecutionPermit",
    "LeaseOwnershipError",
    "LeaseRecord",
    "MigrationControlSettings",
    "PublicationMode",
    "SQLiteLeaseStore",
    "build_idempotency_key",
]
