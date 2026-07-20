"""Leitura da entrada e publicação dos lotes no DataPool do Maestro."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Iterable

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
    """Mantém só os campos do DataPool, sem aplicar regras de negócio."""
    return {field: (row.get(field) or "").strip() for field in DATAPOOL_FIELDS}


def iter_csv_rows(csv_path: Path) -> Iterable[dict[str, str]]:
    """Lê o CSV usando cabeçalho, sem depender da posição das colunas."""
    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = [field for field in DATAPOOL_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                "CSV sem campos obrigatórios para publicação: " + ", ".join(missing)
            )
        for row in reader:
            yield normalize_row(row)


def dispatch_csv(
    csv_path: Path,
    maestro_client: MaestroClient,
    logger: logging.Logger | None = None,
) -> int:
    """Publica cada linha do CSV como item em FilaAuditoriaLotes."""
    current_logger = logger or logging.getLogger(__name__)
    current_logger.info("Iniciando auditoria de acessos")

    published = 0
    for item in iter_csv_rows(csv_path):
        maestro_client.create_entry(item)
        published += 1

    current_logger.info("Itens publicados no DataPool: %s", published)
    return published
