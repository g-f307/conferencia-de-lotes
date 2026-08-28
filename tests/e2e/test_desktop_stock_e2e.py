"""E2E opcional da aplicação Windows e do driver visual real."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.desktop_stock.collector import DesktopStockCollector
from src.desktop_stock.driver import PyAutoGuiDesktopDriver
from src.desktop_stock.models import DesktopCollectionContext
from src.retry_policy import LinearRetryPolicy


@pytest.mark.e2e
@pytest.mark.skipif(
    sys.platform != "win32" or os.getenv("RUN_DESKTOP_E2E") != "1",
    reason=(
        "requer Windows com sessão gráfica dedicada e RUN_DESKTOP_E2E=1; "
        "a CI valida o mesmo contrato com driver injetável"
    ),
)
def test_real_visual_driver_collects_stock_from_simulator(tmp_path: Path) -> None:
    configured_evidence_dir = os.getenv("DESKTOP_E2E_EVIDENCE_DIR", "").strip()
    evidence_dir = (
        Path(configured_evidence_dir).resolve()
        if configured_evidence_dir
        else tmp_path
    )
    simulator = subprocess.Popen(
        [sys.executable, "-m", "src.desktop_stock.simulator"],
    )
    try:
        collector = DesktopStockCollector(
            PyAutoGuiDesktopDriver(),
            LinearRetryPolicy(
                max_attempts=2,
                base_interval_seconds=0.5,
                timeout_seconds=5.0,
            ),
            evidence_dir=evidence_dir,
        )
        result = collector.collect(
            DesktopCollectionContext(
                execution_id="desktop-e2e",
                correlation_id="desktop-e2e",
                root_task_id="root-e2e",
                task_id="task-e2e",
                parent_task_id="dispatcher-e2e",
                expected_items=5,
            )
        )
    finally:
        simulator.terminate()
        simulator.wait(timeout=5)

    assert result["status"] == "SUCCESS", result["payload"]
    assert result["payload"]["collected_items"] == 5
    assert result["artifacts"]
    evidence_path = Path(result["artifacts"][0]["path"])
    assert evidence_path.is_file()
    assert evidence_path.stat().st_size > 0
