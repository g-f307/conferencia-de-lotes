from datetime import datetime, timezone
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.web_automation import (
    WebAutomationTimeoutError,
    WebFormData,
    build_evidence_path,
    fill_and_submit_lote,
    resolve_web_url,
)


class FakeLocator:
    def __init__(self, timeout=False):
        self.actions = []
        self.timeout = timeout

    def fill(self, value):
        self.actions.append(("fill", value))

    def select_option(self, value):
        self.actions.append(("select_option", value))

    def check(self):
        self.actions.append(("check",))

    def click(self):
        self.actions.append(("click",))

    def wait_for(self, state):
        self.actions.append(("wait_for", state))
        if self.timeout:
            raise PlaywrightTimeoutError("timeout de teste")

    def screenshot(self, path):
        self.actions.append(("screenshot", path))


class FakePage:
    def __init__(self, confirmation_timeout=False):
        self.opened_url = None
        self.locators = {}
        self.confirmation_timeout = confirmation_timeout

    def goto(self, url):
        self.opened_url = url

    def get_by_label(self, label, exact=False):
        key = ("label", label, exact)
        return self.locators.setdefault(key, FakeLocator())

    def get_by_role(self, role, name=None):
        key = ("role", role, name)
        return self.locators.setdefault(
            key,
            FakeLocator(
                timeout=role == "status" and self.confirmation_timeout
            ),
        )


def test_resolve_web_url_converte_caminho_relativo_em_file_url(tmp_path: Path):
    html = tmp_path / "docs" / "index.html"

    resolved = resolve_web_url("docs/index.html", tmp_path)

    assert resolved == html.resolve().as_uri()


def test_resolve_web_url_preserva_url_http(tmp_path: Path):
    url = "https://example.test/lotes"

    assert resolve_web_url(url, tmp_path) == url


def test_fill_and_submit_lote_preenche_seleciona_e_clica(tmp_path):
    page = FakePage()
    artifact_dir = tmp_path / "artefatos"
    data = WebFormData(
        lote_id="LOTE-TESTE-001",
        produto="Scanner",
        status="Concluído",
    )

    evidence_path = fill_and_submit_lote(
        page,
        "file:///tmp/index.html",
        artifact_dir,
        data,
    )

    assert page.opened_url == "file:///tmp/index.html"
    assert page.locators[("label", "Número do lote", False)].actions == [
        ("fill", "LOTE-TESTE-001")
    ]
    assert page.locators[("label", "Produto", False)].actions == [
        ("select_option", "Scanner")
    ]
    assert page.locators[("label", "Concluído", True)].actions == [
        ("check",)
    ]
    assert page.locators[
        ("role", "button", "Processar lote")
    ].actions == [("click",)]
    confirmation_actions = page.locators[("role", "status", None)].actions
    assert confirmation_actions[0] == ("wait_for", "visible")
    assert confirmation_actions[1] == (
        "screenshot",
        str(evidence_path),
    )
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


def test_fill_and_submit_lote_informa_timeout_da_confirmacao(tmp_path):
    page = FakePage(confirmation_timeout=True)

    with pytest.raises(
        WebAutomationTimeoutError,
        match="Mensagem de sucesso.*LOTE-TESTE-002",
    ):
        fill_and_submit_lote(
            page,
            "file:///tmp/index.html",
            tmp_path,
            WebFormData(lote_id="LOTE-TESTE-002"),
        )

    assert not list(tmp_path.glob("*.png"))
