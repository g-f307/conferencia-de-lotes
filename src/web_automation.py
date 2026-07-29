"""Sessão Playwright para a aplicação web controlada de conferência de lotes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from src.pages import (
    FormPage,
    FormPageResultError,
    FormPageTimeoutError,
    LoginPage,
    LoginPageTimeoutError,
)
from src.vault_client import ErpCredential


DEFAULT_WEB_TIMEOUT_SECONDS = 15.0
DEFAULT_CHROMIUM_CANDIDATES = (
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/google-chrome-stable"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
)
EVIDENCE_PREFIXES = {
    "APROVADO": "aprovado",
    "REPROVADO": "reprovado",
    "DIVERGENCIA": "divergencia",
    "REVISAO": "divergencia",
    "ERRO": "erro",
}


@dataclass(frozen=True)
class WebItemResult:
    """Resultado rastreável da interação web de um item."""

    url: str
    resultado_validacao: str
    mensagem_resultado: str
    evidence_path: Path


class WebAutomationTimeoutError(RuntimeError):
    """A página controlada não respondeu dentro do prazo configurado."""


class WebAutomationEvidenceError(RuntimeError):
    """A captura visual obrigatória não pôde ser persistida."""


class WebAutomationEnvironmentError(RuntimeError):
    """O ambiente não possui um Chromium utilizável pelo Playwright."""


def resolve_configured_browser() -> Path | None:
    """Valida o Chromium explicitamente configurado para o Runner."""
    configured = os.getenv("PLAYWRIGHT_CHROMIUM_PATH", "").strip()
    if not configured:
        return None

    path = Path(configured).expanduser()
    if not path.is_file():
        raise WebAutomationEnvironmentError(
            "PLAYWRIGHT_CHROMIUM_PATH aponta para um arquivo inexistente: "
            f"{path}"
        )
    if not os.access(path, os.X_OK):
        raise WebAutomationEnvironmentError(
            "PLAYWRIGHT_CHROMIUM_PATH não possui permissão de execução: "
            f"{path}"
        )
    return path


def resolve_chromium_binary() -> Path | None:
    """Usa a configuração explícita, um navegador do Runner ou o bundle."""
    configured = resolve_configured_browser()
    if configured is not None:
        return configured
    for path in DEFAULT_CHROMIUM_CANDIDATES:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def executable_version(path: Path) -> str:
    """Consulta a versão sem interromper o ciclo quando o comando falha."""
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return f"versão indisponível ({exc.__class__.__name__})"
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else "versão indisponível"


def describe_playwright_environment() -> dict[str, str]:
    """Descreve o navegador sem incluir credenciais ou argumentos sensíveis."""
    browser = resolve_chromium_binary()
    return {
        "engine": "playwright-chromium",
        "browser_path": str(browser) if browser else "playwright-bundled",
        "browser_version": (
            executable_version(browser) if browser else "gerenciada pelo Playwright"
        ),
        "headless": "true",
    }


def resolve_web_url(configured_url: str, base_dir: Path) -> str:
    """Converte caminho local em URL aceita pelo navegador."""
    value = configured_url.strip()
    if not value:
        raise ValueError("WEB_TEST_URL deve ser informado")
    if urlparse(value).scheme:
        return value

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve().as_uri()


def resolve_login_url(application_url: str) -> str:
    """Resolve a tela de login associada ao formulário configurado."""
    parsed = urlparse(application_url)
    if parsed.path.rstrip("/").endswith("/login.html"):
        return application_url
    return urljoin(application_url, "login.html")


def build_evidence_path(
    artifact_dir: Path,
    lote_id: object,
    resultado: str,
    timestamp: datetime | None = None,
) -> Path:
    """Monta nome seguro conforme a classificação produzida pelo domínio."""
    safe_lote_id = re.sub(r"[^\w.-]+", "-", str(lote_id or "").strip()).strip("-")
    safe_lote_id = safe_lote_id or "lote-sem-id"
    normalized_result = resultado.strip().upper()
    prefix = EVIDENCE_PREFIXES.get(normalized_result, "erro")
    current_time = timestamp or datetime.now(timezone.utc)
    suffix = current_time.strftime("%Y%m%dT%H%M%S%fZ")
    return artifact_dir / f"{prefix}-{safe_lote_id}-{suffix}.png"


def relative_evidence_path(path: Path, base_dir: Path) -> str:
    """Retorna caminho portátil para logs, resumo e campos do DataPool."""
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return path.name


class PlaywrightWebSession:
    """Mantém uma sessão autenticada e processa os itens individualmente."""

    def __init__(
        self,
        configured_url: str,
        base_dir: Path,
        artifact_dir: Path,
        *,
        timeout_seconds: float = DEFAULT_WEB_TIMEOUT_SECONDS,
        headless: bool = True,
        playwright_factory: Callable[[], Any] = sync_playwright,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero")
        self.url = resolve_web_url(configured_url, base_dir)
        self.base_dir = base_dir
        self.artifact_dir = artifact_dir
        self.timeout_seconds = timeout_seconds
        self.timeout_ms = timeout_seconds * 1_000
        self.headless = headless
        self.playwright_factory = playwright_factory
        self._manager: Any | None = None
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._page: Any | None = None

    def start(self, credential: ErpCredential) -> None:
        """Inicia Chromium headless, autentica e valida a página de lotes."""
        if self._page is not None:
            return
        self._manager = self.playwright_factory()
        self._playwright = self._manager.start()

        launch_options: dict[str, Any] = {
            "headless": self.headless,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        browser_path = resolve_chromium_binary()
        if browser_path is not None:
            launch_options["executable_path"] = str(browser_path)

        try:
            self._browser = self._playwright.chromium.launch(**launch_options)
            self._page = self._browser.new_page(
                viewport={"width": 1440, "height": 1200},
            )
            self._page.set_default_timeout(self.timeout_ms)
            self._page.goto(
                resolve_login_url(self.url),
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            LoginPage(self._page, self.timeout_seconds).fazer_login(
                credential.username,
                credential.password,
            )
        except Exception:
            self.close()
            raise

    def process_item(
        self,
        item: Mapping[str, object],
        resultado_validacao: str,
        mensagem_resultado: str,
    ) -> WebItemResult:
        """Preenche, valida e captura uma evidência específica do item."""
        form_page = FormPage(self._require_page(), self.timeout_seconds)
        dados_interface = {
            **dict(item),
            "resultado_validacao": resultado_validacao,
            "mensagem_resultado": mensagem_resultado,
        }
        try:
            form_page.preencher_lote(dados_interface)
            message = form_page.validar_resultado(resultado_validacao)
        except (LoginPageTimeoutError, FormPageTimeoutError) as exc:
            raise WebAutomationTimeoutError(
                "Fluxo web excedeu o tempo configurado para o item"
            ) from exc
        except FormPageResultError as exc:
            raise WebAutomationEvidenceError(str(exc)) from exc

        evidence_path = build_evidence_path(
            self.artifact_dir,
            item.get("lote_id"),
            resultado_validacao,
        )
        try:
            form_page.capturar_evidencia(evidence_path)
        except (FormPageTimeoutError, FormPageResultError) as exc:
            raise WebAutomationEvidenceError(
                "Não foi possível gerar a evidência visual do item"
            ) from exc

        return WebItemResult(
            url=self.url,
            resultado_validacao=resultado_validacao,
            mensagem_resultado=message,
            evidence_path=evidence_path,
        )

    def capture_error(self, item: Mapping[str, object]) -> Path | None:
        """Tenta registrar o estado atual da página após uma falha isolada."""
        if self._page is None:
            return None
        destination = build_evidence_path(
            self.artifact_dir,
            item.get("lote_id"),
            "ERRO",
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._page.screenshot(path=str(destination), full_page=True)
        except Exception:
            return None
        return destination if destination.is_file() and destination.stat().st_size else None

    def close(self) -> None:
        """Libera página, navegador e runtime, mesmo após falhas."""
        for resource in (self._page, self._browser):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._page = None
        self._browser = None
        self._playwright = None
        self._manager = None

    def _require_page(self) -> Any:
        if self._page is None:
            raise WebAutomationEnvironmentError(
                "Sessão Playwright deve ser iniciada antes do processamento"
            )
        return self._page

    def __enter__(self) -> "PlaywrightWebSession":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()
