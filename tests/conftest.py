"""Fixtures compartilhadas pelos testes E2E com navegador real."""

from pathlib import Path
from typing import Any

import pytest

from src.pages import FormPage
from src.web_automation import resolve_chromium_binary


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORM_PAGE_PATH = PROJECT_ROOT / "web" / "index-lotes" / "index.html"


@pytest.fixture(scope="session")
def browser_type_launch_args(
    browser_type_launch_args: dict[str, Any],
) -> dict[str, Any]:
    """Executa headless e reutiliza um Chromium do ambiente quando disponivel."""
    launch_args = {
        **browser_type_launch_args,
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }
    browser_path = resolve_chromium_binary()
    if browser_path is not None:
        launch_args["executable_path"] = str(browser_path)
    return launch_args


@pytest.fixture
def pagina_html(page: Any) -> Any:
    """Abre o formulario controlado em uma pagina real do Playwright."""
    page.goto(FORM_PAGE_PATH.as_uri(), wait_until="domcontentloaded")
    page.get_by_role(
        "heading",
        name="Processar novo lote",
        exact=True,
    ).wait_for(state="visible")
    return page


@pytest.fixture
def formulario_page(pagina_html: Any) -> FormPage:
    """Fornece o Page Object conectado ao navegador real."""
    return FormPage(pagina_html)
