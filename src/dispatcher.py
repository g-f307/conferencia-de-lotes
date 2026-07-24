"""Leitura da entrada e publicacao dos lotes no DataPool do Maestro."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Iterable

from src.config import Settings
from src.logging_config import LOGGER_NAME
from src.maestro_client import MaestroClient


DATAPOOL_FIELDS = (
    "lote_id",
    "produto",
    "linha",
    "turno",
    "status",
    "responsavel",
    "data",
    "observacao",
)


def normalize_row(row: dict[str, str | None]) -> dict[str, str]:
    """Mantem so os campos do DataPool, sem aplicar regras de negocio."""
    return {field: (row.get(field) or "").strip() for field in DATAPOOL_FIELDS}


def iter_csv_rows(csv_path: Path) -> Iterable[dict[str, str]]:
    """Le o CSV com cabecalho e exige exatamente as oito colunas oficiais."""
    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        fieldnames = tuple(reader.fieldnames or ())
        missing = [field for field in DATAPOOL_FIELDS if field not in fieldnames]
        unexpected = [field for field in fieldnames if field not in DATAPOOL_FIELDS]
        if missing or unexpected:
            details = []
            if missing:
                details.append("campos ausentes: " + ", ".join(missing))
            if unexpected:
                details.append("campos inesperados: " + ", ".join(unexpected))
            raise ValueError(
                "CSV deve conter exatamente os campos do DataPool: " + "; ".join(details)
            )

        for row in reader:
            yield normalize_row(row)


def dispatch_csv(
    csv_path: Path,
    maestro_client: MaestroClient,
    ambiente: str | None = None,
    logger: logging.Logger | None = None,
) -> int:
    """Publica cada linha do CSV como item em FilaAuditoriaLotes2."""
    current_logger = logger or logging.getLogger(LOGGER_NAME)
    current_logger.info(
        "Iniciando auditoria de acessos",
        extra={
            "evento": "INICIO_AUDITORIA",
            "formulario": "Dispatcher",
            "status": "STARTED",
            "usuario": "sistema",
            "ambiente": ambiente,
        },
    )

    published = 0
    for item in iter_csv_rows(csv_path):
        maestro_client.create_entry(item)
        published += 1

    current_logger.info(
        "Itens publicados no DataPool: %s",
        published,
        extra={
            "evento": "PUBLICACAO_DATAPOOL",
            "formulario": "Dispatcher",
            "status": "SUCCESS",
            "usuario": "sistema",
            "ambiente": ambiente,
        },
    )

    return published


def run(
    settings: Settings | None = None,
    maestro_client: MaestroClient | None = None,
    logger: logging.Logger | None = None,
) -> int:
    """Executa o Dispatcher usando o INPUT_CSV configurado."""
    current_settings = settings or Settings.from_env()
    client = maestro_client or MaestroClient(current_settings)

    ambiente = "runner" if current_settings.runner_context else "local"

    return dispatch_csv(
        current_settings.input_csv,
        client,
        logger=logger,
        ambiente=ambiente,
    )


def main() -> int:
    """Entry point para alimentar o DataPool a partir do CSV."""
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
