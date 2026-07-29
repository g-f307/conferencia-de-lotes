from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.pages import FormPageTimeoutError, LoginPageTimeoutError
from src.vault_client import ErpCredential
from src.web_automation import (
    WebAutomationEnvironmentError,
    WebAutomationEvidenceError,
    WebAutomationTimeoutError,
    WebFormData,
    build_chrome_driver,
    build_evidence_path,
    describe_selenium_environment,
    executable_version,
    fill_and_submit_lote,
    resolve_chrome_binary,
    resolve_chromedriver_binary,
    resolve_configured_executable,
    resolve_login_url,
    resolve_web_url,
    run_web_automation,
)


class FakeDriver:
    def __init__(self):
        self.opened_url = None
        self.quit_called = False

    def get(self, url):
        self.opened_url = url

    def quit(self):
        self.quit_called = True


def install_page_object_fakes(
    monkeypatch,
    *,
    success=True,
    login_error=None,
    form_error=None,
    screenshot_succeeds=True,
    screenshot_writes_file=True,
):
    state = {
        "login_instances": [],
        "form_instances": [],
        "login_calls": [],
        "form_calls": [],
        "evidence_calls": [],
    }

    class FakeLoginPage:
        def __init__(self, driver, timeout_seconds):
            state["login_instances"].append((driver, timeout_seconds))

        def fazer_login(self, usuario, senha):
            state["login_calls"].append((usuario, senha))
            if login_error is not None:
                raise login_error

    class FakeFormPage:
        def __init__(self, driver, timeout_seconds):
            state["form_instances"].append((driver, timeout_seconds))

        def preencher_lote(self, dados_lote):
            state["form_calls"].append(dados_lote)
            if form_error is not None:
                raise form_error

        def is_sucesso(self):
            return success

        def capturar_evidencia(self, destino):
            state["evidence_calls"].append(destino)
            if screenshot_succeeds and screenshot_writes_file:
                destino.write_bytes(b"fake-png")
            return screenshot_succeeds

    monkeypatch.setattr("src.web_automation.LoginPage", FakeLoginPage)
    monkeypatch.setattr("src.web_automation.FormPage", FakeFormPage)
    return state


def test_build_chrome_driver_configura_headless_e_webdriver_manager(
    monkeypatch,
):
    captured = {}
    monkeypatch.delenv("CHROMEDRIVER_PATH", raising=False)
    monkeypatch.delenv("CHROME_BIN", raising=False)
    monkeypatch.setattr("src.web_automation.DEFAULT_CHROME_BIN_CANDIDATES", ())
    monkeypatch.setattr("src.web_automation.DEFAULT_CHROMEDRIVER_CANDIDATES", ())
    monkeypatch.setattr(
        "src.web_automation.ChromeDriverManager.install",
        lambda self: "/tmp/chromedriver",
    )
    monkeypatch.setattr(
        "src.web_automation.Service",
        lambda path: type("FakeService", (), {"path": path})(),
    )

    def fake_chrome(*, service, options):
        captured["service"] = service
        captured["options"] = options
        return object()

    monkeypatch.setattr("src.web_automation.webdriver.Chrome", fake_chrome)

    build_chrome_driver(headless=True)

    assert captured["service"].path == "/tmp/chromedriver"
    assert "--headless=new" in captured["options"].arguments
    assert "--no-sandbox" in captured["options"].arguments
    assert "--disable-dev-shm-usage" in captured["options"].arguments
    assert "--disable-crash-reporter" in captured["options"].arguments


def test_build_chrome_driver_usa_binarios_configurados(monkeypatch, tmp_path):
    chrome = tmp_path / "chrome"
    driver = tmp_path / "chromedriver"
    chrome.write_text("#!/bin/sh\n", encoding="utf-8")
    driver.write_text("#!/bin/sh\n", encoding="utf-8")
    chrome.chmod(0o755)
    driver.chmod(0o755)
    monkeypatch.setenv("CHROME_BIN", str(chrome))
    monkeypatch.setenv("CHROMEDRIVER_PATH", str(driver))
    monkeypatch.setattr(
        "src.web_automation.Service",
        lambda path: type("FakeService", (), {"path": path})(),
    )
    monkeypatch.setattr(
        "src.web_automation.ChromeDriverManager.install",
        lambda self: pytest.fail("webdriver-manager nao deveria ser chamado"),
    )
    captured = {}

    def fake_chrome(*, service, options):
        captured["service"] = service
        captured["options"] = options
        return object()

    monkeypatch.setattr("src.web_automation.webdriver.Chrome", fake_chrome)

    build_chrome_driver()

    assert captured["service"].path == str(driver)
    assert captured["options"].binary_location == str(chrome)


def test_resolve_configured_executable_rejeita_caminho_invalido(monkeypatch, tmp_path):
    missing = tmp_path / "chromedriver"
    monkeypatch.setenv("CHROMEDRIVER_PATH", str(missing))

    with pytest.raises(WebAutomationEnvironmentError, match="inexistente"):
        resolve_configured_executable("CHROMEDRIVER_PATH")


def test_resolve_configured_executable_rejeita_sem_permissao(monkeypatch, tmp_path):
    driver = tmp_path / "chromedriver"
    driver.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("CHROMEDRIVER_PATH", str(driver))
    monkeypatch.setattr("src.web_automation.os.access", lambda path, mode: False)

    with pytest.raises(WebAutomationEnvironmentError, match="permissão de execução"):
        resolve_configured_executable("CHROMEDRIVER_PATH")


def test_resolve_chrome_binary_usa_caminho_padrao_quando_env_ausente(
    monkeypatch,
    tmp_path,
):
    chrome = tmp_path / "google-chrome"
    chrome.write_text("#!/bin/sh\n", encoding="utf-8")
    chrome.chmod(0o755)
    monkeypatch.delenv("CHROME_BIN", raising=False)
    monkeypatch.setattr("src.web_automation.DEFAULT_CHROME_BIN_CANDIDATES", (chrome,))

    assert resolve_chrome_binary() == chrome


def test_resolve_chromedriver_binary_usa_caminho_padrao_quando_env_ausente(
    monkeypatch,
    tmp_path,
):
    driver = tmp_path / "chromedriver"
    driver.write_text("#!/bin/sh\n", encoding="utf-8")
    driver.chmod(0o755)
    monkeypatch.delenv("CHROMEDRIVER_PATH", raising=False)
    monkeypatch.setattr(
        "src.web_automation.DEFAULT_CHROMEDRIVER_CANDIDATES",
        (driver,),
    )

    assert resolve_chromedriver_binary() == driver


def test_describe_selenium_environment_inclui_versoes_configuradas(
    monkeypatch,
    tmp_path,
):
    chrome = tmp_path / "chrome"
    driver = tmp_path / "chromedriver"
    chrome.write_text("#!/bin/sh\n", encoding="utf-8")
    driver.write_text("#!/bin/sh\n", encoding="utf-8")
    chrome.chmod(0o755)
    driver.chmod(0o755)
    monkeypatch.setenv("CHROME_BIN", str(chrome))
    monkeypatch.setenv("CHROMEDRIVER_PATH", str(driver))
    monkeypatch.setattr(
        "src.web_automation.executable_version",
        lambda path: f"{path.name} 1.0",
    )

    environment = describe_selenium_environment()

    assert environment == {
        "chrome_bin": str(chrome),
        "chrome_version": "chrome 1.0",
        "chromedriver_path": str(driver),
        "chromedriver_version": "chromedriver 1.0",
    }


def test_executable_version_retorna_primeira_linha(monkeypatch, tmp_path):
    binary = tmp_path / "chrome"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")

    class Completed:
        stdout = "Chrome 120\nsegunda linha"
        stderr = ""

    monkeypatch.setattr(
        "src.web_automation.subprocess.run",
        lambda *args, **kwargs: Completed(),
    )

    assert executable_version(binary) == "Chrome 120"


def test_resolve_web_url_converte_caminho_relativo_em_file_url(tmp_path: Path):
    html = tmp_path / "docs" / "index.html"

    resolved = resolve_web_url("docs/index.html", tmp_path)

    assert resolved == html.resolve().as_uri()


def test_resolve_web_url_preserva_url_http(tmp_path: Path):
    url = "https://example.test/lotes"

    assert resolve_web_url(url, tmp_path) == url


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


def test_fill_and_submit_lote_orquestra_page_objects_com_mesmo_driver(
    tmp_path,
    monkeypatch,
):
    driver = FakeDriver()
    artifact_dir = tmp_path / "artefatos"
    credential = ErpCredential(
        username="usuario.erp",
        password="senha-nao-logavel",
    )
    data = WebFormData(
        lote_id="LOTE-TESTE-001",
        produto="Scanner",
        status="Concluído",
    )
    state = install_page_object_fakes(monkeypatch)

    evidence_path = fill_and_submit_lote(
        driver,
        "file:///tmp/web/index-lotes/index.html",
        artifact_dir,
        credential,
        data,
        timeout_seconds=15,
    )

    assert driver.opened_url == "file:///tmp/web/index-lotes/login.html"
    assert state["login_instances"] == [(driver, 15)]
    assert state["form_instances"] == [(driver, 15)]
    assert state["login_calls"] == [
        ("usuario.erp", "senha-nao-logavel"),
    ]
    assert state["form_calls"] == [
        {
            "lote_id": "LOTE-TESTE-001",
            "produto": "Scanner",
            "status": "Concluído",
        }
    ]
    assert state["evidence_calls"] == [evidence_path]
    assert evidence_path.is_file()
    assert evidence_path.parent == artifact_dir
    assert "LOTE-TESTE-001" in evidence_path.name


def test_build_evidence_path_identifica_lote_e_momento(tmp_path):
    timestamp = datetime(2026, 7, 23, 4, 30, tzinfo=timezone.utc)

    path = build_evidence_path(
        tmp_path,
        "LOTE / 001",
        timestamp=timestamp,
    )

    assert path == (
        tmp_path / "comprovante-LOTE-001-20260723T043000000000Z.png"
    )


@pytest.mark.parametrize(
    "page_error",
    [
        LoginPageTimeoutError("login indisponivel"),
        FormPageTimeoutError("formulario indisponivel"),
    ],
)
def test_fill_and_submit_lote_normaliza_timeout_sem_expor_senha(
    tmp_path,
    monkeypatch,
    page_error,
):
    credential = ErpCredential("usuario.erp", "segredo-nao-pode-vazar")
    kwargs = (
        {"login_error": page_error}
        if isinstance(page_error, LoginPageTimeoutError)
        else {"form_error": page_error}
    )
    install_page_object_fakes(monkeypatch, **kwargs)

    with pytest.raises(WebAutomationTimeoutError) as captured:
        fill_and_submit_lote(
            FakeDriver(),
            "file:///tmp/web/index-lotes/index.html",
            tmp_path,
            credential,
            WebFormData(lote_id="LOTE-TESTE-002"),
            timeout_seconds=15,
        )

    assert "LOTE-TESTE-002" in str(captured.value)
    assert "segredo-nao-pode-vazar" not in str(captured.value)
    assert not list(tmp_path.glob("*.png"))


def test_fill_and_submit_lote_rejeita_confirmacao_sem_sucesso(
    tmp_path,
    monkeypatch,
):
    install_page_object_fakes(monkeypatch, success=False)

    with pytest.raises(
        WebAutomationTimeoutError,
        match="Mensagem de confirmação inválida.*LOTE-2026-0001",
    ):
        fill_and_submit_lote(
            FakeDriver(),
            "file:///tmp/web/index-lotes/index.html",
            tmp_path,
            ErpCredential("usuario.erp", "senha-efemera"),
        )


@pytest.mark.parametrize(
    ("screenshot_succeeds", "screenshot_writes_file"),
    [(False, False), (True, False)],
)
def test_fill_and_submit_lote_falha_quando_evidencia_nao_e_criada(
    tmp_path,
    monkeypatch,
    screenshot_succeeds,
    screenshot_writes_file,
):
    install_page_object_fakes(
        monkeypatch,
        screenshot_succeeds=screenshot_succeeds,
        screenshot_writes_file=screenshot_writes_file,
    )

    with pytest.raises(
        WebAutomationEvidenceError,
        match="Não foi possível gerar a evidência.*LOTE-2026-0001",
    ):
        fill_and_submit_lote(
            FakeDriver(),
            "file:///tmp/web/index-lotes/index.html",
            tmp_path,
            ErpCredential("usuario.erp", "senha-efemera"),
        )


def test_run_web_automation_sempre_encerra_driver(tmp_path, monkeypatch):
    driver = FakeDriver()
    evidence = tmp_path / "artefatos" / "comprovante.png"

    monkeypatch.setattr(
        "src.web_automation.fill_and_submit_lote",
        lambda *args, **kwargs: evidence,
    )

    result = run_web_automation(
        "docs/index.html",
        tmp_path,
        tmp_path / "artefatos",
        ErpCredential("usuario.erp", "senha-efemera"),
        driver_factory=lambda **kwargs: driver,
    )

    assert result.evidence_path == evidence
    assert driver.quit_called is True


def test_run_web_automation_encerra_driver_apos_falha(tmp_path, monkeypatch):
    driver = FakeDriver()

    def fail(*args, **kwargs):
        raise WebAutomationTimeoutError("timeout")

    monkeypatch.setattr("src.web_automation.fill_and_submit_lote", fail)

    with pytest.raises(WebAutomationTimeoutError):
        run_web_automation(
            "docs/index.html",
            tmp_path,
            tmp_path / "artefatos",
            ErpCredential("usuario.erp", "senha-efemera"),
            driver_factory=lambda **kwargs: driver,
        )

    assert driver.quit_called is True
