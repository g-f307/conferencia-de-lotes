"""Automação resiliente do formulário local de lotes com Selenium."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


DEFAULT_WEB_TIMEOUT_SECONDS = 15.0


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
    """A confirmação esperada não apareceu dentro do prazo configurado."""


class WebAutomationEvidenceError(RuntimeError):
    """A captura visual obrigatória não pôde ser persistida."""


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


def build_chrome_driver(*, headless: bool = True) -> Any:
    """Cria o ChromeDriver local ou usa o binário definido pelo container."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-crash-reporter")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1200")

    chrome_binary = os.getenv("CHROME_BIN", "").strip()
    if chrome_binary:
        options.binary_location = chrome_binary

    configured_driver = os.getenv("CHROMEDRIVER_PATH", "").strip()
    driver_path = configured_driver or ChromeDriverManager().install()
    return webdriver.Chrome(
        service=Service(driver_path),
        options=options,
    )


def _status_label_xpath(status: str) -> str:
    if '"' in status:
        raise ValueError("Status contém caractere inválido para o seletor")
    return (
        f'//label[.//input[@name="status" and @value="{status}"]]'
    )


def fill_and_submit_lote(
    driver: Any,
    url: str,
    artifact_dir: Path,
    form_data: WebFormData | None = None,
    *,
    timeout_seconds: float = DEFAULT_WEB_TIMEOUT_SECONDS,
    wait_factory: Callable[[Any, float], Any] = WebDriverWait,
) -> Path:
    """Preenche o formulário usando waits explícitos no envio e confirmação."""
    data = form_data or WebFormData()
    driver.get(url)

    lote_input = driver.find_element(By.ID, "numero-lote")
    lote_input.clear()
    lote_input.send_keys(data.lote_id)
    driver.find_element(By.ID, "produto").send_keys(data.produto)
    driver.find_element(
        By.XPATH,
        _status_label_xpath(data.status),
    ).click()

    wait = wait_factory(driver, timeout_seconds)
    try:
        button = wait.until(
            EC.element_to_be_clickable((By.ID, "botao-processar"))
        )
    except TimeoutException as exc:
        raise WebAutomationTimeoutError(
            "Botão de processamento não ficou clicável para o lote "
            f"{data.lote_id} em até {timeout_seconds:g} segundos"
        ) from exc

    button.click()
    try:
        confirmation = wait.until(
            EC.visibility_of_element_located((By.ID, "mensagem"))
        )
    except TimeoutException as exc:
        raise WebAutomationTimeoutError(
            "Mensagem de sucesso não ficou visível para o lote "
            f"{data.lote_id} em até {timeout_seconds:g} segundos"
        ) from exc

    if "sucesso" not in confirmation.text.casefold():
        raise WebAutomationTimeoutError(
            "Mensagem de confirmação inválida para o lote "
            f"{data.lote_id}: {confirmation.text!r}"
        )

    artifact_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = build_evidence_path(artifact_dir, data.lote_id)
    screenshot_created = confirmation.screenshot(str(evidence_path))
    if not screenshot_created or not evidence_path.is_file():
        raise WebAutomationEvidenceError(
            "Não foi possível gerar a evidência da automação para o lote "
            f"{data.lote_id}: {evidence_path}"
        )
    return evidence_path


def run_web_automation(
    configured_url: str,
    base_dir: Path,
    artifact_dir: Path,
    form_data: WebFormData | None = None,
    *,
    headless: bool = True,
    timeout_seconds: float = DEFAULT_WEB_TIMEOUT_SECONDS,
    driver_factory: Callable[..., Any] = build_chrome_driver,
) -> WebAutomationResult:
    """Executa a automação Selenium e sempre encerra o ChromeDriver."""
    url = resolve_web_url(configured_url, base_dir)
    driver = driver_factory(headless=headless)
    try:
        evidence_path = fill_and_submit_lote(
            driver,
            url,
            artifact_dir,
            form_data,
            timeout_seconds=timeout_seconds,
        )
    finally:
        driver.quit()
    return WebAutomationResult(url=url, evidence_path=evidence_path)
