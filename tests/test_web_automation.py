from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.vault_client import ErpCredential
from src.web_automation import (
    PlaywrightWebSession,
    WebAutomationEnvironmentError,
    WebItemResult,
    build_evidence_path,
    describe_playwright_environment,
    executable_version,
    relative_evidence_path,
    resolve_chromium_binary,
    resolve_login_url,
    resolve_web_url,
)


class FakePage:
    def __init__(self, state, *, screenshot_error=None):
        self.state = state
        self.screenshot_error = screenshot_error

    def set_default_timeout(self, timeout):
        self.state["timeout"] = timeout

    def goto(self, url, **kwargs):
        self.state["goto"] = (url, kwargs)

    def screenshot(self, *, path, full_page):
        self.state["screenshots"].append((path, full_page))
        if self.screenshot_error is not None:
            raise self.screenshot_error
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-png")

    def close(self):
        self.state["page_closed"] += 1


class FakeBrowser:
    def __init__(self, state, page):
        self.state = state
        self.page = page

    def new_page(self, **kwargs):
        self.state["new_page"] = kwargs
        return self.page

    def close(self):
        self.state["browser_closed"] += 1


class FakeChromium:
    def __init__(self, state, browser):
        self.state = state
        self.browser = browser

    def launch(self, **kwargs):
        self.state["launch"] = kwargs
        return self.browser


class FakePlaywright:
    def __init__(self, state, browser):
        self.state = state
        self.chromium = FakeChromium(state, browser)

    def stop(self):
        self.state["playwright_stopped"] += 1


class FakeManager:
    def __init__(self, playwright):
        self.playwright = playwright

    def start(self):
        return self.playwright


def build_fake_runtime(*, screenshot_error=None):
    state = {
        "screenshots": [],
        "page_closed": 0,
        "browser_closed": 0,
        "playwright_stopped": 0,
    }
    page = FakePage(state, screenshot_error=screenshot_error)
    browser = FakeBrowser(state, page)
    playwright = FakePlaywright(state, browser)
    return state, page, lambda: FakeManager(playwright)


def install_page_object_fakes(monkeypatch, *, form_error=None):
    state = {
        "login_calls": [],
        "form_instances": [],
        "form_calls": [],
        "validation_calls": [],
        "evidence_calls": [],
    }

    class FakeLoginPage:
        def __init__(self, page, timeout_seconds):
            state["login_page"] = (page, timeout_seconds)

        def fazer_login(self, usuario, senha):
            state["login_calls"].append((usuario, senha))

    class FakeFormPage:
        def __init__(self, page, timeout_seconds):
            state["form_page"] = (page, timeout_seconds)
            state["form_instances"].append((page, timeout_seconds))

        def preencher_lote(self, dados_lote):
            state["form_calls"].append(dados_lote)
            if form_error is not None:
                raise form_error

        def validar_resultado(self, resultado):
            state["validation_calls"].append(resultado)
            return f"Resultado confirmado: {resultado}"

        def capturar_evidencia(self, destino):
            state["evidence_calls"].append(destino)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(b"fake-png")

    monkeypatch.setattr("src.web_automation.LoginPage", FakeLoginPage)
    monkeypatch.setattr("src.web_automation.FormPage", FakeFormPage)
    return state


def test_resolve_web_url_converte_caminho_relativo_em_file_url(tmp_path):
    html = tmp_path / "web" / "index.html"

    assert resolve_web_url("web/index.html", tmp_path) == html.resolve().as_uri()


def test_resolve_web_url_preserva_url_http(tmp_path):
    assert (
        resolve_web_url("https://example.test/lotes", tmp_path)
        == "https://example.test/lotes"
    )


def test_resolve_login_url_usa_tela_irma_do_formulario():
    assert (
        resolve_login_url("file:///tmp/web/index-lotes/index.html")
        == "file:///tmp/web/index-lotes/login.html"
    )
    assert (
        resolve_login_url("https://example.test/lotes/index.html")
        == "https://example.test/lotes/login.html"
    )


def test_resolve_login_url_preserva_url_de_login():
    url = "https://example.test/lotes/login.html"
    assert resolve_login_url(url) == url


def test_resolve_chromium_usa_caminho_configurado(monkeypatch, tmp_path):
    browser = tmp_path / "chromium"
    browser.write_text("#!/bin/sh\n", encoding="utf-8")
    browser.chmod(0o755)
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_PATH", str(browser))

    assert resolve_chromium_binary() == browser


def test_resolve_chromium_rejeita_caminho_configurado_inexistente(
    monkeypatch,
    tmp_path,
):
    missing = tmp_path / "chromium"
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_PATH", str(missing))

    with pytest.raises(WebAutomationEnvironmentError, match="inexistente"):
        resolve_chromium_binary()


def test_resolve_chromium_rejeita_arquivo_sem_permissao(monkeypatch, tmp_path):
    browser = tmp_path / "chromium"
    browser.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_PATH", str(browser))
    monkeypatch.setattr("src.web_automation.os.access", lambda path, mode: False)

    with pytest.raises(WebAutomationEnvironmentError, match="permissão"):
        resolve_chromium_binary()


def test_resolve_chromium_usa_bundle_quando_nao_ha_binario(monkeypatch):
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_PATH", raising=False)
    monkeypatch.setattr("src.web_automation.DEFAULT_CHROMIUM_CANDIDATES", ())

    assert resolve_chromium_binary() is None


def test_describe_playwright_environment_inclui_navegador_configurado(
    monkeypatch,
    tmp_path,
):
    browser = tmp_path / "chromium"
    browser.write_text("#!/bin/sh\n", encoding="utf-8")
    browser.chmod(0o755)
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_PATH", str(browser))
    monkeypatch.setattr(
        "src.web_automation.executable_version",
        lambda path: "Chromium 120",
    )

    assert describe_playwright_environment() == {
        "engine": "playwright-chromium",
        "browser_path": str(browser),
        "browser_version": "Chromium 120",
        "headless": "true",
    }


def test_executable_version_retorna_primeira_linha(monkeypatch, tmp_path):
    binary = tmp_path / "chromium"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")

    class Completed:
        stdout = "Chromium 120\nsegunda linha"
        stderr = ""

    monkeypatch.setattr(
        "src.web_automation.subprocess.run",
        lambda *args, **kwargs: Completed(),
    )

    assert executable_version(binary) == "Chromium 120"


@pytest.mark.parametrize(
    ("resultado", "prefixo"),
    [
        ("APROVADO", "aprovado"),
        ("REPROVADO", "reprovado"),
        ("DIVERGENCIA", "divergencia"),
        ("REVISAO", "divergencia"),
        ("ERRO", "erro"),
    ],
)
def test_build_evidence_path_identifica_resultado_lote_e_momento(
    tmp_path,
    resultado,
    prefixo,
):
    timestamp = datetime(2026, 7, 29, 13, 30, tzinfo=timezone.utc)

    path = build_evidence_path(
        tmp_path,
        "LOTE / 001",
        resultado,
        timestamp=timestamp,
    )

    assert path == (
        tmp_path / f"{prefixo}-LOTE-001-20260729T133000000000Z.png"
    )


def test_relative_evidence_path_retorna_caminho_portatil(tmp_path):
    path = tmp_path / "artefatos" / "aprovado-L001.png"
    assert relative_evidence_path(path, tmp_path) == "artefatos/aprovado-L001.png"


def test_sessao_inicia_headless_e_autentica_com_page_object(
    monkeypatch,
    tmp_path,
):
    state, page, factory = build_fake_runtime()
    po_state = install_page_object_fakes(monkeypatch)
    monkeypatch.setattr("src.web_automation.resolve_chromium_binary", lambda: None)
    session = PlaywrightWebSession(
        "web/index-lotes/index.html",
        tmp_path,
        tmp_path / "artefatos",
        timeout_seconds=12,
        playwright_factory=factory,
    )

    session.start(ErpCredential("usuario.vault", "senha-secreta"))

    assert state["launch"]["headless"] is True
    assert "--no-sandbox" in state["launch"]["args"]
    assert "--disable-dev-shm-usage" in state["launch"]["args"]
    assert "--disable-gpu" in state["launch"]["args"]
    assert state["new_page"]["viewport"] == {"width": 1440, "height": 1200}
    assert state["timeout"] == 12_000
    assert state["goto"][0].endswith("/web/index-lotes/login.html")
    assert po_state["login_page"] == (page, 12)
    assert po_state["login_calls"] == [("usuario.vault", "senha-secreta")]


def test_sessao_processa_item_e_gera_evidencia_rastreavel(
    monkeypatch,
    tmp_path,
):
    _, _, factory = build_fake_runtime()
    po_state = install_page_object_fakes(monkeypatch)
    monkeypatch.setattr("src.web_automation.resolve_chromium_binary", lambda: None)
    session = PlaywrightWebSession(
        "web/index-lotes/index.html",
        tmp_path,
        tmp_path / "artefatos",
        playwright_factory=factory,
    )
    session.start(ErpCredential("usuario.vault", "senha-secreta"))

    result = session.process_item(
        {"lote_id": "L001", "produto": "Monitor", "status": "APROVADO"},
        "APROVADO",
        "Lote validado",
    )

    assert isinstance(result, WebItemResult)
    assert result.resultado_validacao == "APROVADO"
    assert result.evidence_path.is_file()
    assert result.evidence_path.name.startswith("aprovado-L001-")
    assert po_state["form_calls"][0]["lote_id"] == "L001"
    assert po_state["form_calls"][0]["resultado_validacao"] == "APROVADO"
    assert po_state["validation_calls"] == ["APROVADO"]
    assert po_state["evidence_calls"] == [result.evidence_path]
    assert len(po_state["form_instances"]) == 1


def test_sessao_instancia_form_page_para_cada_item(monkeypatch, tmp_path):
    _, _, factory = build_fake_runtime()
    po_state = install_page_object_fakes(monkeypatch)
    monkeypatch.setattr("src.web_automation.resolve_chromium_binary", lambda: None)
    session = PlaywrightWebSession(
        "web/index-lotes/index.html",
        tmp_path,
        tmp_path / "artefatos",
        playwright_factory=factory,
    )
    session.start(ErpCredential("usuario.vault", "senha-secreta"))

    for lote_id in ("L001", "L002"):
        session.process_item(
            {"lote_id": lote_id, "produto": "Monitor", "status": "APROVADO"},
            "APROVADO",
            "Lote validado",
        )

    assert len(po_state["form_instances"]) == 2


def test_sessao_captura_evidencia_de_erro_por_item(monkeypatch, tmp_path):
    state, _, factory = build_fake_runtime()
    install_page_object_fakes(monkeypatch)
    monkeypatch.setattr("src.web_automation.resolve_chromium_binary", lambda: None)
    session = PlaywrightWebSession(
        "web/index-lotes/index.html",
        tmp_path,
        tmp_path / "artefatos",
        playwright_factory=factory,
    )
    session.start(ErpCredential("usuario.vault", "senha-secreta"))

    evidence = session.capture_error({"lote_id": "L002"})

    assert evidence is not None
    assert evidence.name.startswith("erro-L002-")
    assert evidence.is_file()
    assert state["screenshots"] == [(str(evidence), True)]


def test_sessao_retorna_none_quando_captura_de_erro_falha(
    monkeypatch,
    tmp_path,
):
    _, _, factory = build_fake_runtime(screenshot_error=RuntimeError("falha"))
    install_page_object_fakes(monkeypatch)
    monkeypatch.setattr("src.web_automation.resolve_chromium_binary", lambda: None)
    session = PlaywrightWebSession(
        "web/index-lotes/index.html",
        tmp_path,
        tmp_path / "artefatos",
        playwright_factory=factory,
    )
    session.start(ErpCredential("usuario.vault", "senha-secreta"))

    assert session.capture_error({"lote_id": "L003"}) is None


def test_sessao_sempre_fecha_pagina_navegador_e_playwright(
    monkeypatch,
    tmp_path,
):
    state, _, factory = build_fake_runtime()
    install_page_object_fakes(monkeypatch)
    monkeypatch.setattr("src.web_automation.resolve_chromium_binary", lambda: None)
    session = PlaywrightWebSession(
        "web/index-lotes/index.html",
        tmp_path,
        tmp_path / "artefatos",
        playwright_factory=factory,
    )
    session.start(ErpCredential("usuario.vault", "senha-secreta"))

    session.close()
    session.close()

    assert state["page_closed"] == 1
    assert state["browser_closed"] == 1
    assert state["playwright_stopped"] == 1
