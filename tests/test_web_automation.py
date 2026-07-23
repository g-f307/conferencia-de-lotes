from pathlib import Path

from src.web_automation import WebFormData, fill_and_submit_lote, resolve_web_url


class FakeLocator:
    def __init__(self):
        self.actions = []

    def fill(self, value):
        self.actions.append(("fill", value))

    def select_option(self, value):
        self.actions.append(("select_option", value))

    def check(self):
        self.actions.append(("check",))

    def click(self):
        self.actions.append(("click",))


class FakePage:
    def __init__(self):
        self.opened_url = None
        self.locators = {}

    def goto(self, url):
        self.opened_url = url

    def locator(self, selector):
        return self.locators.setdefault(selector, FakeLocator())


def test_resolve_web_url_converte_caminho_relativo_em_file_url(tmp_path: Path):
    html = tmp_path / "docs" / "index.html"

    resolved = resolve_web_url("docs/index.html", tmp_path)

    assert resolved == html.resolve().as_uri()


def test_resolve_web_url_preserva_url_http(tmp_path: Path):
    url = "https://example.test/lotes"

    assert resolve_web_url(url, tmp_path) == url


def test_fill_and_submit_lote_preenche_seleciona_e_clica():
    page = FakePage()
    data = WebFormData(
        lote_id="LOTE-TESTE-001",
        produto="Scanner",
        status="Concluído",
    )

    fill_and_submit_lote(page, "file:///tmp/index.html", data)

    assert page.opened_url == "file:///tmp/index.html"
    assert page.locators["#numero-lote"].actions == [
        ("fill", "LOTE-TESTE-001")
    ]
    assert page.locators["#produto"].actions == [
        ("select_option", "Scanner")
    ]
    assert page.locators[
        'input[name="status"][value="Concluído"]'
    ].actions == [("check",)]
    assert page.locators["#botao-processar"].actions == [("click",)]
