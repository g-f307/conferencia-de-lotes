import json
from pathlib import Path

import pytest

from src.supplier_portal import (
    SupplierOrder,
    SupplierPortalCollector,
    SupplierPortalConfig,
    SupplierSessionResult,
    write_collection_result,
)

pytestmark = pytest.mark.integration


class ControlledSession:
    def __init__(self, result: SupplierSessionResult) -> None:
        self.result = result

    def collect(self) -> SupplierSessionResult:
        return self.result


def test_bot_independente_persiste_contrato_para_a_consolidacao(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidencias" / "coleta.png"
    evidence.parent.mkdir()
    evidence.write_bytes(b"\x89PNG\r\n\x1a\ncontrolled")
    orders = (
        SupplierOrder(
            pedido_id="PED-1001",
            lote_id="L001",
            fornecedor="Alfa Componentes",
            produto="Monitor",
            quantidade_solicitada=20,
            status_pedido="CONFIRMADO",
            data_prevista="28/08/2026",
        ),
    )
    config = SupplierPortalConfig(
        url="web/supplier-portal/index.html",
        username="fornecedor.demo",
        password="senha-controlada",
        execution_id="exec-integration-001",
        correlation_id="corr-integration-001",
        root_task_id="root-integration-001",
        task_id="task-web-integration-001",
        parent_task_id="task-dispatcher-integration-001",
        artifact_dir=tmp_path / "evidencias",
        max_attempts=1,
    )
    result = SupplierPortalCollector(
        config,
        session_factory=lambda _attempt: ControlledSession(
            SupplierSessionResult(orders, evidence)
        ),
    ).collect()
    destination = write_collection_result(
        result, tmp_path / "data" / "fornecedores.json"
    )

    persisted = json.loads(destination.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == "1.0"
    assert persisted["correlation_id"] == "corr-integration-001"
    assert persisted["payload"]["records"][0]["pedido_id"] == "PED-1001"
    assert persisted["payload"]["latency_ms"] >= 0
    assert persisted["artifacts"][0]["type"] == "image/png"
    assert "senha-controlada" not in destination.read_text(encoding="utf-8")


def test_portal_controlado_disponibiliza_todos_os_campos_do_contrato() -> None:
    html = Path("web/supplier-portal/index.html").read_text(encoding="utf-8")

    for expected in (
        "Pedido",
        "Lote",
        "Fornecedor",
        "Produto",
        "Quantidade",
        "Status",
        "Data prevista",
    ):
        assert f">{expected}<" in html
