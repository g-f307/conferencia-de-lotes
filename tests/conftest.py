"""Fixtures compartilhadas pelas camadas da suite automatizada."""

from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook

from src.pages import FormPage
from src.web_automation import resolve_chromium_binary

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORM_PAGE_PATH = PROJECT_ROOT / "web" / "index-lotes" / "index.html"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--capstone-evidence-dir",
        action="store",
        default="",
        help="Persiste evidências locais sanitizadas dos cenários do Capstone.",
    )


@pytest.fixture(scope="session")
def capstone_evidence_dir(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    configured = str(request.config.getoption("--capstone-evidence-dir") or "").strip()
    destination = (
        Path(configured).expanduser()
        if configured
        else tmp_path_factory.mktemp("capstone-evidencias")
    )
    if not destination.is_absolute():
        destination = PROJECT_ROOT / destination
    destination.mkdir(parents=True, exist_ok=True)
    return destination.resolve()


@pytest.fixture
def registros_validos() -> list[dict[str, object]]:
    """Fornece registros validos sem depender da massa oficial do projeto."""
    return [
        {
            "lote_id": "L001",
            "produto": "Monitor",
            "linha": "Linha A",
            "turno": "Manhã",
            "status": "APROVADO",
            "responsavel": "Gabriel",
            "data": "14/06/2026",
            "observacao": "",
        },
        {
            "lote_id": "L002",
            "produto": "Teclado",
            "linha": "Linha B",
            "turno": "Tarde",
            "status": "NOK",
            "responsavel": "Marcelo",
            "data": "14/06/2026",
            "observacao": "Avaria identificada",
        },
    ]


@pytest.fixture
def base_referencia_simulada() -> list[dict[str, object]]:
    """Representa a resposta controlada da Base de Referencia externa."""
    return [
        {"lote_id": lote_id, "produto": produto}
        for lote_id, produto in (
            ("L001", "Monitor"),
            ("L002", "Teclado"),
            ("L003", "Mouse"),
            ("L004", "Notebook"),
            ("L005", "Impressora"),
        )
    ]


@pytest.fixture
def registros_invalidos() -> list[dict[str, object]]:
    """Fornece divergencia, ambiguidade e erro de entrada controlados."""
    return [
        {
            "lote_id": "L999",
            "produto": "Monitor",
            "linha": "Linha A",
            "turno": "Manhã",
            "status": "APROVADO",
            "responsavel": "Rebecca",
            "data": "14/06/2026",
            "observacao": "",
        },
        {
            "lote_id": "L003",
            "produto": "Mouse",
            "linha": "Linha A",
            "turno": "Tarde",
            "status": "em análise",
            "responsavel": "Rebecca",
            "data": "14/06/2026",
            "observacao": "",
        },
        {
            "lote_id": "L004",
            "produto": "Notebook",
            "linha": "Linha B",
            "turno": "Noite",
            "status": "APROVADO",
            "responsavel": "Gabriel",
            "data": "2026-06-14",
            "observacao": "",
        },
        {
            "lote_id": "L005",
            "produto": "Impressora",
            "linha": "Linha B",
            "turno": "Noite",
            "status": "REPROVADO",
            "responsavel": "Marcelo",
            "data": "14/06/2026",
            "observacao": "",
        },
    ]


@pytest.fixture
def workbook_sintetico(
    tmp_path: Path,
    registros_validos: list[dict[str, object]],
    registros_invalidos: list[dict[str, object]],
) -> Path:
    """Cria a entrada Excel usada na integracao dentro do diretorio temporario."""
    workbook_path = tmp_path / "entrada_sintetica.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Insp_14_06_2026"
    sheet.append(["Conferência controlada de lotes"])
    sheet.append([])
    headers = (
        "lote_id",
        "produto",
        "linha",
        "turno",
        "status",
        "responsavel",
        "data",
        "observacao",
    )
    sheet.append(headers)
    for registro in [*registros_validos, *registros_invalidos]:
        sheet.append([registro.get(header, "") for header in headers])
    workbook.save(workbook_path)
    workbook.close()
    return workbook_path


@pytest.fixture
def diretorio_saida(tmp_path: Path) -> Path:
    """Reserva um diretorio temporario para relatorios, logs e arquivos parciais."""
    output_dir = tmp_path / "saida"
    output_dir.mkdir()
    return output_dir


@pytest.fixture(scope="session")
def browser_type_launch_args(
    browser_type_launch_args: dict[str, Any],
) -> dict[str, Any]:
    """Executa headless e reutiliza um Chromium do ambiente quando disponivel."""
    launch_args = {
        **browser_type_launch_args,
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
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
