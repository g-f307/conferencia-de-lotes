"""Ponto de entrada independente do bot ``relatorio-alertas-v2``."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.alerts import construir_sistema_alertas
from src.config import Settings
from src.logging_config import configure_logging
from src.migration_control import (
    CoexistenceCoordinator,
    MigrationControlSettings,
    SQLiteLeaseStore,
)

from .models import CapstoneReportInputError, build_report_snapshot
from .service import CapstoneReportService


@dataclass(frozen=True)
class CapstoneReportSettings:
    input_path: Path
    output_dir: Path
    degraded_alert_seconds: float

    @classmethod
    def from_env(cls) -> CapstoneReportSettings:
        threshold = float(os.getenv("CAPSTONE_DEGRADED_ALERT_SECONDS", "300"))
        if threshold < 0:
            raise ValueError("CAPSTONE_DEGRADED_ALERT_SECONDS não pode ser negativo")
        return cls(
            input_path=Path(
                os.getenv(
                    "CAPSTONE_REPORT_INPUT_PATH",
                    "data/output/pipeline-capstone.json",
                )
            ),
            output_dir=Path(
                os.getenv("CAPSTONE_REPORT_DIR", "relatorios/capstone")
            ),
            degraded_alert_seconds=threshold,
        )


def run(settings: CapstoneReportSettings | None = None) -> dict[str, Any]:
    current = settings or CapstoneReportSettings.from_env()
    if not current.input_path.is_file():
        raise FileNotFoundError(
            f"Entrada do relatório inexistente: {current.input_path}"
        )
    payload = json.loads(current.input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CapstoneReportInputError("entrada do relatório deve ser um objeto JSON")

    application_settings = Settings.from_env()
    application_settings.validate()
    logger = configure_logging(
        application_settings.log_file,
        application_settings,
    )
    alerts = construir_sistema_alertas(application_settings, logger)
    coexistence = None
    permit = None
    if os.getenv("MIGRATION_CONTROL_ENABLED", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "sim",
        "on",
    }:
        migration_snapshot = build_report_snapshot(payload)
        migration_settings = MigrationControlSettings.from_env(
            application_settings.base_dir
        )
        coexistence = CoexistenceCoordinator(
            SQLiteLeaseStore(migration_settings.database_path),
            migration_settings,
            logger=logger,
        )
        permit = coexistence.begin_execution(
            migration_snapshot.execution_id,
            owner_id=migration_snapshot.root_task_id,
        )

    try:
        result = CapstoneReportService(
            current.output_dir,
            alerts=alerts,
            degraded_alert_seconds=current.degraded_alert_seconds,
            logger=logger,
            coexistence=coexistence,
            migration_permit=permit,
        ).generate(payload)
        return result.to_dict()
    finally:
        if coexistence is not None and permit is not None:
            coexistence.release(permit)


def main() -> int:
    load_dotenv()
    try:
        result = run()
    except (CapstoneReportInputError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"status": "FAILED", "error_type": type(exc).__name__},
                ensure_ascii=False,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "SUCCESS",
                "report_type": result["report_type"],
                "execution_id": result["execution_id"],
                "summary_path": result["summary_path"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
