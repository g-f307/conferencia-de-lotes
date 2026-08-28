"""Ponto de entrada do bot de coleta desktop."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.desktop_stock.collector import DesktopStockCollector
from src.desktop_stock.driver import PyAutoGuiDesktopDriver
from src.desktop_stock.models import DesktopCollectionContext
from src.retry_policy import LinearRetryPolicy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coletar o estoque pela interface")
    parser.add_argument("--output", type=Path, default=Path("data/output/desktop-stock.json"))
    parser.add_argument("--evidence-dir", type=Path, default=Path("data/output/evidencias-desktop"))
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--attempts", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    context = DesktopCollectionContext(
        execution_id=os.getenv("EXECUTION_ID", "desktop-local"),
        correlation_id=os.getenv("CORRELATION_ID", "desktop-local"),
        root_task_id=os.getenv("ROOT_TASK_ID", "dispatcher-local"),
        task_id=os.getenv("TASK_ID", "desktop-task-local"),
        parent_task_id=os.getenv("PARENT_TASK_ID", "dispatcher-local"),
        expected_items=int(os.getenv("EXPECTED_ITEMS", "0")),
    )
    collector = DesktopStockCollector(
        PyAutoGuiDesktopDriver(),
        LinearRetryPolicy(
            max_attempts=args.attempts,
            base_interval_seconds=1.0,
            timeout_seconds=args.timeout,
        ),
        evidence_dir=args.evidence_dir,
    )
    result = collector.collect(context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if result["status"] == "SUCCESS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
