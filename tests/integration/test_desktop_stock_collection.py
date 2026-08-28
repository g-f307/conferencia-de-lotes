"""Integração controlada entre driver visual e contrato do coletor desktop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.desktop_stock.collector import DesktopStockCollector
from src.desktop_stock.models import DesktopCollectionContext
from src.retry_policy import LinearRetryPolicy

VISIBLE_STOCK = """lote_id\tproduto\tquantidade_disponivel\tlocalizacao\tstatus_estoque\tatualizado_em
L001\tMonitor\t18\tA-01\tDISPONIVEL\t2026-08-26T12:00:00+00:00
L002\tTeclado\t4\tA-02\tBAIXO\t2026-08-26T12:02:00+00:00"""


class ControlledVisualDriver:
    """Dublê da fronteira visual, sem acesso a arquivo ou API de negócio."""

    def wait_until_ready(self, timeout_seconds: float) -> None:
        return None

    def search(self, query: str, timeout_seconds: float) -> None:
        assert query == "*"

    def read_visible_records(self, timeout_seconds: float) -> str:
        return VISIBLE_STOCK

    def capture_evidence(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"controlled-screenshot")
        return destination

    def close(self) -> None:
        return None


@pytest.mark.integration
def test_desktop_collection_serializes_only_visible_interface_data(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "evidence"
    output_path = tmp_path / "desktop-result.json"
    driver = ControlledVisualDriver()
    collector = DesktopStockCollector(
        driver,
        LinearRetryPolicy(
            max_attempts=1,
            base_interval_seconds=0.01,
            timeout_seconds=1.0,
        ),
        evidence_dir=evidence_dir,
    )

    envelope = collector.collect(
        DesktopCollectionContext(
            execution_id="integration-001",
            correlation_id="corr-integration",
            root_task_id="root-integration",
            task_id="desktop-integration",
            parent_task_id="dispatcher-integration",
            expected_items=2,
        )
    )
    output_path.write_text(json.dumps(envelope), encoding="utf-8")
    persisted = json.loads(output_path.read_text(encoding="utf-8"))

    assert persisted["schema_version"] == "1.0"
    assert persisted["predecessor_task_ids"] == ["dispatcher-integration"]
    assert len(persisted["payload"]["records"]) == 2
    assert set(persisted["payload"]["records"][0]) == {
        "lote_id",
        "produto",
        "quantidade_disponivel",
        "localizacao",
        "status_estoque",
        "atualizado_em",
    }
    assert Path(persisted["payload"]["evidence_paths"][0]).is_file()
