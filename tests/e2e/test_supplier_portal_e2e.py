import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.pages import SupplierPortalAuthenticationError, SupplierPortalPage

pytestmark = [pytest.mark.e2e, pytest.mark.browser]
PORTAL_PATH = Path(__file__).resolve().parents[2] / "web" / "supplier-portal"


def test_page_object_autentica_e_coleta_pedidos_em_navegador_real(
    page,
    tmp_path: Path,
) -> None:
    page.goto((PORTAL_PATH / "login.html").as_uri(), wait_until="domcontentloaded")
    portal = SupplierPortalPage(page, timeout_seconds=5)

    portal.autenticar("fornecedor.demo", "demo-local")
    orders = portal.coletar_pedidos()
    evidence = portal.capturar_evidencia(tmp_path / "portal-fornecedores.png")

    assert len(orders) == 4
    assert orders[0] == {
        "pedido_id": "PED-1001",
        "lote_id": "L001",
        "fornecedor": "Alfa Componentes",
        "produto": "Monitor",
        "quantidade_solicitada": 20,
        "status_pedido": "CONFIRMADO",
        "data_prevista": "28/08/2026",
    }
    assert evidence.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_page_object_diferencia_falha_de_autenticacao(
    page, tmp_path: Path
) -> None:
    page.goto((PORTAL_PATH / "login.html").as_uri(), wait_until="domcontentloaded")

    with pytest.raises(SupplierPortalAuthenticationError, match="recusou"):
        SupplierPortalPage(page, timeout_seconds=5).autenticar(
            "fornecedor.demo", "credencial-invalida"
        )

    evidence = tmp_path / "autenticacao-recusada.png"
    page.screenshot(path=str(evidence), full_page=True)
    assert evidence.is_file()


def test_coletor_independente_executa_portal_completo(tmp_path: Path) -> None:
    result_path = tmp_path / "fornecedores.json"
    environment = {
        **os.environ,
        "SUPPLIER_PORTAL_URL": str(PORTAL_PATH / "index.html"),
        "SUPPLIER_PORTAL_USERNAME": "fornecedor.demo",
        "SUPPLIER_PORTAL_PASSWORD": "demo-local",
        "SUPPLIER_ARTIFACT_DIR": str(tmp_path / "evidencias"),
        "SUPPLIER_RESULT_PATH": str(result_path),
        "SUPPLIER_TIMEOUT_SECONDS": "5",
        "SUPPLIER_MAX_ATTEMPTS": "1",
        "EXECUTION_ID": "exec-browser-001",
        "CORRELATION_ID": "corr-browser-001",
        "ROOT_TASK_ID": "root-browser-001",
        "TASK_ID": "task-web-browser-001",
        "PARENT_TASK_ID": "task-dispatcher-browser-001",
    }

    completed = subprocess.run(
        [sys.executable, "-m", "src.supplier_portal_bot"],
        cwd=PORTAL_PATH.parents[1],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert completed.returncode == 0, completed.stderr
    assert result["status"] == "SUCCESS"
    assert result["payload"]["collected_items"] == 4
    assert result["payload"]["failed_items"] == 0
    assert result["attempts"] == 1
    assert len(result["artifacts"]) == 1
    assert Path(result["artifacts"][0]["path"]).is_file()
