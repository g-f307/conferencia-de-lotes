"""Coleta independente de pedidos no portal controlado de fornecedores."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.pages import (
    SupplierPortalAuthenticationError as PageAuthenticationError,
)
from src.pages import (
    SupplierPortalDataError as PageDataError,
)
from src.pages import (
    SupplierPortalPage,
    SupplierPortalPageTimeoutError,
)
from src.retry_policy import LinearRetryPolicy, RetryExhaustedError
from src.web_automation import resolve_chromium_binary

BOT_ID = "fornecedores-web-v1"
TRIGGER_BOT = "dispatcher-v2"
SCHEMA_VERSION = "1.0"


class SupplierPortalError(RuntimeError):
    """Erro controlado da fronteira web, opcionalmente acompanhado de evidência."""

    def __init__(self, message: str, evidence_path: Path | None = None) -> None:
        super().__init__(message)
        self.evidence_path = evidence_path


class SupplierPortalUnavailableError(SupplierPortalError):
    """O portal ou o navegador não pôde ser acessado."""


class SupplierPortalTimeoutError(SupplierPortalError):
    """O portal excedeu o timeout configurado."""


class SupplierPortalAuthenticationError(SupplierPortalError):
    """As credenciais foram recusadas pelo portal."""


class SupplierPortalDataError(SupplierPortalError):
    """Um pedido exibido pelo portal não respeita o contrato."""


@dataclass(frozen=True)
class SupplierOrder:
    """Pedido normalizado pela fronteira visual do portal."""

    pedido_id: str
    lote_id: str
    fornecedor: str
    produto: str
    quantidade_solicitada: int
    status_pedido: str
    data_prevista: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> SupplierOrder:
        required = (
            "pedido_id",
            "lote_id",
            "fornecedor",
            "produto",
            "quantidade_solicitada",
            "status_pedido",
            "data_prevista",
        )
        normalized = {key: str(data.get(key, "")).strip() for key in required}
        missing = [key for key, value in normalized.items() if not value]
        if missing:
            raise SupplierPortalDataError(
                "Pedido possui campos obrigatórios vazios: " + ", ".join(missing)
            )
        try:
            quantity = int(normalized["quantidade_solicitada"])
        except ValueError as exc:
            raise SupplierPortalDataError(
                "Pedido possui quantidade_solicitada inválida"
            ) from exc
        if quantity <= 0:
            raise SupplierPortalDataError(
                "Pedido possui quantidade_solicitada não positiva"
            )
        return cls(
            pedido_id=normalized["pedido_id"],
            lote_id=normalized["lote_id"],
            fornecedor=normalized["fornecedor"],
            produto=normalized["produto"],
            quantidade_solicitada=quantity,
            status_pedido=normalized["status_pedido"],
            data_prevista=normalized["data_prevista"],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "pedido_id": self.pedido_id,
            "lote_id": self.lote_id,
            "fornecedor": self.fornecedor,
            "produto": self.produto,
            "quantidade_solicitada": self.quantidade_solicitada,
            "status_pedido": self.status_pedido,
            "data_prevista": self.data_prevista,
        }


@dataclass(frozen=True)
class SupplierPortalConfig:
    """Configuração não global do bot; a senha nunca aparece em ``repr``."""

    url: str
    username: str
    password: str = field(repr=False)
    execution_id: str = "local-execution"
    correlation_id: str = "local-correlation"
    root_task_id: str = "local-root-task"
    task_id: str = "local-supplier-task"
    parent_task_id: str | None = None
    artifact_dir: Path = Path("artefatos/fornecedores")
    timeout_seconds: float = 15.0
    max_attempts: int = 3
    retry_interval_seconds: float = 1.0
    headless: bool = True

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("url do portal deve ser informada")
        for name in ("execution_id", "correlation_id", "root_task_id", "task_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} deve ser informado")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero")
        if isinstance(self.max_attempts, bool) or self.max_attempts < 1:
            raise ValueError("max_attempts deve ser um inteiro maior que zero")
        if (
            not math.isfinite(self.retry_interval_seconds)
            or self.retry_interval_seconds <= 0
        ):
            raise ValueError("retry_interval_seconds deve ser maior que zero")


@dataclass(frozen=True)
class SupplierSessionResult:
    orders: tuple[SupplierOrder, ...]
    evidence_path: Path


class SupplierPortalSession(Protocol):
    def collect(self) -> SupplierSessionResult: ...


def resolve_supplier_url(configured_url: str, base_dir: Path | None = None) -> str:
    """Transforma caminho local ou URL em destino navegável."""
    value = configured_url.strip()
    if not value:
        raise ValueError("url do portal deve ser informada")
    if urlparse(value).scheme.lower() in {"file", "http", "https"}:
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base_dir or Path.cwd()) / path
    return path.resolve().as_uri()


def resolve_supplier_login_url(application_url: str) -> str:
    parsed = urlparse(application_url)
    if parsed.path.rstrip("/").endswith("/login.html"):
        return application_url
    return urljoin(application_url, "login.html")


def build_supplier_evidence_path(
    artifact_dir: Path,
    execution_id: str,
    attempt: int,
    *,
    outcome: str = "success",
    now: datetime | None = None,
) -> Path:
    safe_execution = re.sub(r"[^\w.-]+", "-", execution_id).strip("-")
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")
    return artifact_dir / (
        f"supplier-{outcome}-{safe_execution or 'execution'}-"
        f"attempt-{attempt}-{timestamp}.png"
    )


class PlaywrightSupplierPortalSession:
    """Sessão curta: cada retry abre e encerra um navegador próprio."""

    def __init__(
        self,
        config: SupplierPortalConfig,
        attempt: int,
        *,
        playwright_factory: Callable[[], Any] = sync_playwright,
    ) -> None:
        self.config = config
        self.attempt = attempt
        self.playwright_factory = playwright_factory

    def collect(self) -> SupplierSessionResult:
        manager: Any | None = None
        playwright: Any | None = None
        browser: Any | None = None
        page: Any | None = None
        try:
            manager = self.playwright_factory()
            playwright = manager.start()
            options: dict[str, object] = {
                "headless": self.config.headless,
                "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            }
            browser_path = resolve_chromium_binary()
            if browser_path is not None:
                options["executable_path"] = str(browser_path)
            browser = playwright.chromium.launch(**options)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(self.config.timeout_seconds * 1_000)
            page.goto(
                resolve_supplier_login_url(resolve_supplier_url(self.config.url)),
                wait_until="domcontentloaded",
                timeout=self.config.timeout_seconds * 1_000,
            )
            portal = SupplierPortalPage(page, self.config.timeout_seconds)
            portal.autenticar(self.config.username, self.config.password)
            orders = tuple(
                SupplierOrder.from_mapping(order)
                for order in portal.coletar_pedidos()
            )
            evidence = portal.capturar_evidencia(
                build_supplier_evidence_path(
                    self.config.artifact_dir,
                    self.config.execution_id,
                    self.attempt,
                )
            )
            return SupplierSessionResult(orders=orders, evidence_path=evidence)
        except PageAuthenticationError as exc:
            raise SupplierPortalAuthenticationError(str(exc)) from exc
        except PageDataError as exc:
            evidence = self._capture_failure(page)
            raise SupplierPortalDataError(str(exc), evidence) from exc
        except (SupplierPortalPageTimeoutError, PlaywrightTimeoutError) as exc:
            evidence = self._capture_failure(page)
            raise SupplierPortalTimeoutError(
                "O portal excedeu o timeout configurado", evidence
            ) from exc
        except (PlaywrightError, OSError) as exc:
            evidence = self._capture_failure(page)
            detail = str(exc).replace(self.config.password, "[REDACTED]")
            detail = detail.replace(self.config.username, "[REDACTED]").strip()
            raise SupplierPortalUnavailableError(
                "O portal ou o navegador está indisponível"
                + (f": {detail[:500]}" if detail else ""),
                evidence,
            ) from exc
        finally:
            for resource in (page, browser):
                if resource is not None:
                    with suppress(PlaywrightError):
                        resource.close()
            if playwright is not None:
                with suppress(PlaywrightError):
                    playwright.stop()

    def _capture_failure(self, page: Any | None) -> Path | None:
        if page is None:
            return None
        destination = build_supplier_evidence_path(
            self.config.artifact_dir,
            self.config.execution_id,
            self.attempt,
            outcome="failure",
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(destination), full_page=True)
        except PlaywrightError:
            return None
        return destination if destination.is_file() and destination.stat().st_size else None


class SupplierPortalCollector:
    """Aplica retry somente às falhas transitórias e sempre termina em envelope."""

    def __init__(
        self,
        config: SupplierPortalConfig,
        *,
        session_factory: Callable[[int], SupplierPortalSession] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.config = config
        self.session_factory = session_factory or (
            lambda attempt: PlaywrightSupplierPortalSession(config, attempt)
        )
        self.sleep = sleep
        self.clock = clock
        self.now = now

    def collect(self) -> dict[str, object]:
        started = self.clock()
        started_at = self.now().astimezone(timezone.utc)
        attempt_counter = 0
        evidence_paths: list[Path] = []

        def operation(_timeout_seconds: float) -> SupplierSessionResult:
            nonlocal attempt_counter
            attempt_counter += 1
            try:
                result = self.session_factory(attempt_counter).collect()
            except SupplierPortalError as exc:
                if exc.evidence_path is not None:
                    evidence_paths.append(exc.evidence_path)
                raise
            evidence_paths.append(result.evidence_path)
            return result

        policy = LinearRetryPolicy(
            max_attempts=self.config.max_attempts,
            base_interval_seconds=self.config.retry_interval_seconds,
            timeout_seconds=self.config.timeout_seconds,
            sleep=self.sleep,
            clock=self.clock,
        )
        try:
            retry_result = policy.execute(
                operation,
                retry_on=(SupplierPortalUnavailableError, SupplierPortalTimeoutError),
            )
        except RetryExhaustedError as exc:
            error = exc.last_error
            return self._failure_envelope(
                error,
                attempts=exc.attempts,
                latency_ms=self._latency_ms(started),
                evidence_paths=evidence_paths,
                started_at=started_at,
            )
        except (SupplierPortalAuthenticationError, SupplierPortalDataError) as exc:
            return self._failure_envelope(
                exc,
                attempts=max(attempt_counter, 1),
                latency_ms=self._latency_ms(started),
                evidence_paths=evidence_paths,
                started_at=started_at,
            )

        return self._envelope(
            status="SUCCESS",
            source_status="AVAILABLE",
            attempts=retry_result.attempts,
            latency_ms=self._latency_ms(started),
            orders=retry_result.value.orders,
            evidence_paths=evidence_paths,
            started_at=started_at,
        )

    def _failure_envelope(
        self,
        error: Exception,
        *,
        attempts: int,
        latency_ms: int,
        evidence_paths: list[Path],
        started_at: datetime,
    ) -> dict[str, object]:
        failure_type, fallback_reason = {
            SupplierPortalUnavailableError: ("UNAVAILABLE", "source_unavailable"),
            SupplierPortalTimeoutError: ("TIMEOUT", "timeout"),
            SupplierPortalAuthenticationError: (
                "AUTHENTICATION",
                "authentication_failed",
            ),
            SupplierPortalDataError: ("INVALID_DATA", "invalid_source_data"),
        }[type(error)]
        return self._envelope(
            status="FAILED",
            source_status="UNAVAILABLE",
            attempts=attempts,
            latency_ms=latency_ms,
            orders=(),
            evidence_paths=evidence_paths,
            started_at=started_at,
            motivo_fallback=fallback_reason,
            failure_type=failure_type,
            failure_message=str(error),
        )

    def _envelope(
        self,
        *,
        status: str,
        source_status: str,
        attempts: int,
        latency_ms: int,
        orders: tuple[SupplierOrder, ...],
        evidence_paths: list[Path],
        started_at: datetime,
        motivo_fallback: str | None = None,
        failure_type: str | None = None,
        failure_message: str | None = None,
    ) -> dict[str, object]:
        completed_at = self.now().astimezone(timezone.utc)
        unique_evidence = list(dict.fromkeys(evidence_paths))
        artifacts = [self._artifact(path) for path in unique_evidence if path.is_file()]
        payload: dict[str, object] = {
            "records": [order.to_dict() for order in orders],
            "source_status": source_status,
            "collected_items": len(orders),
            "failed_items": 0 if status == "SUCCESS" else 1,
            "latency_ms": latency_ms,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "evidence_paths": [artifact["path"] for artifact in artifacts],
        }
        if failure_type is not None:
            payload["failure_type"] = failure_type
            payload["failure_message"] = failure_message
        return {
            "schema_version": SCHEMA_VERSION,
            "execution_id": self.config.execution_id,
            "correlation_id": self.config.correlation_id,
            "root_task_id": self.config.root_task_id,
            "task_id": self.config.task_id,
            "parent_task_id": self.config.parent_task_id,
            "predecessor_task_ids": (
                [self.config.parent_task_id] if self.config.parent_task_id else []
            ),
            "bot_id": BOT_ID,
            "trigger_bot": TRIGGER_BOT,
            "timestamp": completed_at.isoformat(),
            "status": status,
            "origem_dados": ["web"] if status == "SUCCESS" else ["fallback"],
            "modo_degradado": status != "SUCCESS",
            "motivo_fallback": motivo_fallback,
            "attempts": attempts,
            "payload": payload,
            "artifacts": artifacts,
        }

    @staticmethod
    def _artifact(path: Path) -> dict[str, str]:
        return {
            "name": path.name,
            "type": "image/png",
            "path": path.as_posix(),
            "checksum": sha256(path.read_bytes()).hexdigest(),
        }

    def _latency_ms(self, started: float) -> int:
        return max(0, round((self.clock() - started) * 1_000))


def write_collection_result(result: Mapping[str, object], path: Path) -> Path:
    """Persiste o envelope JSON para o estágio seguinte do pipeline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path
