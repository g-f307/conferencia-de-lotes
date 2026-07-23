"""Automação inicial do formulário local de lotes com Playwright."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class WebFormData:
    """Dados seguros usados para demonstrar o preenchimento do formulário."""

    lote_id: str = "LOTE-2026-0001"
    produto: str = "Monitor"
    status: str = "Pendente"


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


def fill_and_submit_lote(
    page: Any,
    url: str,
    form_data: WebFormData | None = None,
) -> None:
    """Abre a página, preenche o formulário e aciona seu envio."""
    data = form_data or WebFormData()
    page.goto(url)
    page.get_by_label("Número do lote").fill(data.lote_id)
    page.get_by_label("Produto").select_option(data.produto)
    page.get_by_label(data.status, exact=True).check()
    page.get_by_role("button", name="Processar lote").click()


def run_web_automation(
    configured_url: str,
    base_dir: Path,
    form_data: WebFormData | None = None,
    *,
    headless: bool = True,
) -> str:
    """Executa a automação em Chromium e devolve a URL efetivamente aberta."""
    from playwright.sync_api import sync_playwright

    url = resolve_web_url(configured_url, base_dir)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            fill_and_submit_lote(page, url, form_data)
        finally:
            browser.close()
    return url
