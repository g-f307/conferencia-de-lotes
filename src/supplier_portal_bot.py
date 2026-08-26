"""Ponto de entrada independente do bot ``fornecedores-web-v1``."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from src.supplier_portal import (
    SupplierPortalCollector,
    SupplierPortalConfig,
    write_collection_result,
)


def build_config_from_environment() -> SupplierPortalConfig:
    """Monta configuração sem imprimir ou persistir a senha."""
    execution_id = os.getenv("EXECUTION_ID", f"local-{uuid4()}").strip()
    return SupplierPortalConfig(
        url=os.getenv(
            "SUPPLIER_PORTAL_URL", "web/supplier-portal/index.html"
        ),
        username=os.getenv("SUPPLIER_PORTAL_USERNAME", ""),
        password=os.getenv("SUPPLIER_PORTAL_PASSWORD", ""),
        execution_id=execution_id,
        correlation_id=os.getenv("CORRELATION_ID", execution_id),
        root_task_id=os.getenv("ROOT_TASK_ID", f"root-{execution_id}"),
        task_id=os.getenv("TASK_ID", f"web-{execution_id}"),
        parent_task_id=os.getenv("PARENT_TASK_ID") or None,
        artifact_dir=Path(
            os.getenv("SUPPLIER_ARTIFACT_DIR", "artefatos/fornecedores")
        ),
        timeout_seconds=float(os.getenv("SUPPLIER_TIMEOUT_SECONDS", "15")),
        max_attempts=int(os.getenv("SUPPLIER_MAX_ATTEMPTS", "3")),
        retry_interval_seconds=float(
            os.getenv("SUPPLIER_RETRY_INTERVAL_SECONDS", "1")
        ),
        headless=os.getenv("SUPPLIER_HEADLESS", "true").strip().lower()
        not in {"0", "false", "no"},
    )


def main() -> int:
    config = build_config_from_environment()
    result = SupplierPortalCollector(config).collect()
    destination = Path(
        os.getenv("SUPPLIER_RESULT_PATH", "data/output/fornecedores.json")
    )
    write_collection_result(result, destination)
    print(
        json.dumps(
            {
                "status": result["status"],
                "execution_id": result["execution_id"],
                "result_path": destination.as_posix(),
                "collected_items": result["payload"]["collected_items"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
