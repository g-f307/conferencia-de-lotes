"""Configuração do log local e console exigido pelo processo."""

import json
import logging
import sys

from datetime import UTC, datetime
from pathlib import Path

LOGGER_NAME = "auditor_lotes"

class StructuredJsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                UTC,
            ).isoformat(),
            "level": record.levelname,
            "evento": getattr(record, "evento", "LOG"),
            "aplicacao": getattr(
                record,
                "aplicacao",
                "bot-conferencia-de-lotes-v1",
            ),
            "ambiente": getattr(record, "ambiente", "local"),
            "usuario": getattr(record, "usuario", "sistema"),
            "detalhes": {
                "formulario": getattr(record, "formulario", None),
                "status": getattr(record, "status", None),
                "mensagem": record.getMessage(),
            },
        }

        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )


def configure_logging(log_file: Path) -> logging.Logger:
    """Cria logger de arquivo e console com data, hora, severidade e mensagem."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    formatter = StructuredJsonFormatter()

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
