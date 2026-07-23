"""Automação inicial do formulário local de lotes com Playwright."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


@dataclass(frozen=True)
class WebFormData:
    """Dados seguros usados para demonstrar o preenchimento do formulário."""

    lote_id: str = "LOTE-2026-0001"
    produto: str = "Monitor"
    status: str = "Pendente"


@dataclass(frozen=True)
class WebAutomationResult:
    """Resultado da interação web e sua evidência visual."""

    url: str
    evidence_path: Path


class WebAutomationTimeoutError(RuntimeError):
    """A confirmação esperada não apareceu dentro do prazo do Playwright."""


def resolve_web_url(configured_url: str, base_dir: Path) -> str:
    """Converte um caminho local configurado em uma URL aceita pelo navegador."""
    value = configured_url.strip()
    if not value:
        raise ValueError("WEB_TEST_URL deve ser informado")

    if urlparse(value).scheme:
        return value

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve().as_uri()


def build_evidence_path(
    artifact_dir: Path,
    lote_id: str,
    timestamp: datetime | None = None,
) -> Path:
    """Monta um nome seguro e rastreável para a evidência do lote."""
    safe_lote_id = re.sub(r"[^\w.-]+", "-", lote_id.strip()).strip("-")
    safe_lote_id = safe_lote_id or "lote-sem-id"
    current_time = timestamp or datetime.now(timezone.utc)
    suffix = current_time.strftime("%Y%m%dT%H%M%S%fZ")
    return artifact_dir / f"comprovante-{safe_lote_id}-{suffix}.png"


def fill_and_submit_lote(
    page: Any,
    url: str,
    artifact_dir: Path,
    form_data: WebFormData | None = None,
) -> Path:
    """Abre a página, preenche o formulário e aciona seu envio."""
    data = form_data or WebFormData()
    page.goto(url)
    page.get_by_label("Número do lote").fill(data.lote_id)
    page.get_by_label("Produto").select_option(data.produto)
    page.get_by_label(data.status, exact=True).check()
    page.get_by_role("button", name="Processar lote").click()
    confirmation = page.get_by_role("status")

    try:
        confirmation.wait_for(state="visible")
    except PlaywrightTimeoutError as exc:
        raise WebAutomationTimeoutError(
            "Mensagem de sucesso não ficou visível para o lote "
            f"{data.lote_id}"
        ) from exc

    artifact_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = build_evidence_path(artifact_dir, data.lote_id)
    confirmation.screenshot(path=str(evidence_path))
    return evidence_path


def run_web_automation(
    configured_url: str,
    base_dir: Path,
    artifact_dir: Path,
    form_data: WebFormData | None = None,
    *,
    headless: bool = True,
) -> WebAutomationResult:
    """Executa a automação em Chromium e devolve URL e evidência."""
    from playwright.sync_api import sync_playwright

    url = resolve_web_url(configured_url, base_dir)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            evidence_path = fill_and_submit_lote(
                page,
                url,
                artifact_dir,
                form_data,
            )
        finally:
            browser.close()
    return WebAutomationResult(url=url, evidence_path=evidence_path)
