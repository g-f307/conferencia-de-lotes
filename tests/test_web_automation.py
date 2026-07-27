from datetime import datetime, timezone
from pathlib import Path

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from src.web_automation import (
    WebAutomationTimeoutError,
    WebFormData,
    build_chrome_driver,
    build_evidence_path,
    fill_and_submit_lote,
    resolve_web_url,
    run_web_automation,
)


class FakeElement:
    def __init__(self, text="", displayed=True, enabled=True):
        self.actions = []
        self.text = text
        self.displayed = displayed
        self.enabled = enabled

    def clear(self):
        self.actions.append(("clear",))

    def send_keys(self, value):
        self.actions.append(("send_keys", value))

    def click(self):
        self.actions.append(("click",))

    def screenshot(self, path):
        self.actions.append(("screenshot", path))
        return True

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled


class FakeDriver:
    def __init__(
        self,
        *,
        confirmation_visible=True,
        confirmation_text="Lote processado com sucesso.",
        button_enabled=True,
    ):
        self.opened_url = None
        self.quit_called = False
        self.elements = {
            (By.ID, "numero-lote"): FakeElement(),
            (By.ID, "produto"): FakeElement(),
            (
                By.XPATH,
                '//label[.//input[@name="status" and @value="Concluído"]]',
            ): FakeElement(),
            (
                By.XPATH,
                '//label[.//input[@name="status" and @value="Pendente"]]',
            ): FakeElement(),
            (By.ID, "botao-processar"): FakeElement(enabled=button_enabled),
            (By.ID, "mensagem"): FakeElement(
                text=confirmation_text,
                displayed=confirmation_visible,
            ),
        }

    def get(self, url):
        self.opened_url = url

    def find_element(self, by, value):
        return self.elements[(by, value)]

    def quit(self):
        self.quit_called = True


class ImmediateWait:
    def __init__(self, driver, timeout):
        self.driver = driver
        self.timeout = timeout

    def until(self, condition):
        result = condition(self.driver)
        if not result:
            raise TimeoutException("timeout de teste")
        return result


class DelayedConfirmationWait(ImmediateWait):
    def until(self, condition):
        result = condition(self.driver)
        if result:
            return result
        self.driver.elements[(By.ID, "mensagem")].displayed = True
        result = condition(self.driver)
        if not result:
            raise TimeoutException("timeout de teste")
        return result


def test_build_chrome_driver_configura_headless_e_webdriver_manager(
    monkeypatch,
):
    captured = {}
    monkeypatch.delenv("CHROMEDRIVER_PATH", raising=False)
    monkeypatch.delenv("CHROME_BIN", raising=False)
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


def test_resolve_web_url_converte_caminho_relativo_em_file_url(tmp_path: Path):
    html = tmp_path / "docs" / "index.html"

    resolved = resolve_web_url("docs/index.html", tmp_path)

    assert resolved == html.resolve().as_uri()


def test_resolve_web_url_preserva_url_http(tmp_path: Path):
    url = "https://example.test/lotes"

    assert resolve_web_url(url, tmp_path) == url


def test_fill_and_submit_lote_usa_selenium_e_waits_explicitos(tmp_path):
    driver = FakeDriver()
    artifact_dir = tmp_path / "artefatos"
    data = WebFormData(
        lote_id="LOTE-TESTE-001",
        produto="Scanner",
        status="Concluído",
    )

    evidence_path = fill_and_submit_lote(
        driver,
        "file:///tmp/index.html",
        artifact_dir,
        data,
        timeout_seconds=15,
        wait_factory=ImmediateWait,
    )

    assert driver.opened_url == "file:///tmp/index.html"
    assert driver.elements[(By.ID, "numero-lote")].actions == [
        ("clear",),
        ("send_keys", "LOTE-TESTE-001"),
    ]
    assert driver.elements[(By.ID, "produto")].actions == [
        ("send_keys", "Scanner")
    ]
    assert driver.elements[
        (
            By.XPATH,
            '//label[.//input[@name="status" and @value="Concluído"]]',
        )
    ].actions == [("click",)]
    assert driver.elements[(By.ID, "botao-processar")].actions == [
        ("click",)
    ]
    assert driver.elements[(By.ID, "mensagem")].actions == [
        ("screenshot", str(evidence_path))
    ]
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
    ("driver", "expected_message"),
    [
        (
            FakeDriver(confirmation_visible=False),
            "Mensagem de sucesso.*LOTE-TESTE-002.*15 segundos",
        ),
        (
            FakeDriver(button_enabled=False),
            "Botão de processamento.*LOTE-TESTE-002.*15 segundos",
        ),
    ],
)
def test_fill_and_submit_lote_informa_timeout(
    tmp_path,
    driver,
    expected_message,
):
    with pytest.raises(WebAutomationTimeoutError, match=expected_message):
        fill_and_submit_lote(
            driver,
            "file:///tmp/index.html",
            tmp_path,
            WebFormData(lote_id="LOTE-TESTE-002"),
            timeout_seconds=15,
            wait_factory=ImmediateWait,
        )

    assert not list(tmp_path.glob("*.png"))


def test_fill_and_submit_lote_suporta_confirmacao_atrasada(tmp_path):
    driver = FakeDriver(confirmation_visible=False)

    evidence_path = fill_and_submit_lote(
        driver,
        "file:///tmp/index.html",
        tmp_path,
        wait_factory=DelayedConfirmationWait,
    )

    assert evidence_path.parent == tmp_path
    assert driver.elements[(By.ID, "mensagem")].displayed is True


def test_fill_and_submit_lote_rejeita_confirmacao_sem_sucesso(tmp_path):
    driver = FakeDriver(confirmation_text="Falha ao processar o lote.")

    with pytest.raises(
        WebAutomationTimeoutError,
        match="Mensagem de confirmação inválida",
    ):
        fill_and_submit_lote(
            driver,
            "file:///tmp/index.html",
            tmp_path,
            wait_factory=ImmediateWait,
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
            driver_factory=lambda **kwargs: driver,
        )

    assert driver.quit_called is True
