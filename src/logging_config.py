"""Configuração do log local e console exigido pelo processo."""

import json
import logging
import sys

from datetime import UTC, datetime
from pathlib import Path

from src.config import Settings

LOGGER_NAME = "auditor_lotes"


def resolve_log_environment(record: logging.LogRecord) -> str:
    """Resolve o ambiente sem fixar local quando a execucao vem do Runner."""
    ambiente = getattr(record, "ambiente", None)
    if ambiente:
        return str(ambiente)
    return "runner" if Settings.from_env().runner_context else "local"


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
            "ambiente": resolve_log_environment(record),
            "usuario": getattr(record, "usuario", "sistema"),
            "detalhes": {
                "formulario": getattr(record, "formulario", None),
                "status": getattr(record, "status", None),
                "mensagem": record.getMessage(),
            },
        }

        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            payload["detalhes"]["exception"] = self.formatException(record.exc_info)
            payload["detalhes"]["exception_type"] = (
                exc_type.__name__ if exc_type else None
            )
            payload["detalhes"]["exception_message"] = str(exc_value)

        return json.dumps(
            payload,
            ensure_ascii=False,
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
