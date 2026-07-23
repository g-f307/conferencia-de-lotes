"""Configuração do log local e console exigido pelo processo."""

import json
import logging
import os
import re
import sys

from datetime import UTC, datetime
from pathlib import Path

from src.config import Settings

LOGGER_NAME = "auditor_lotes"
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(password|senha|token|api[_-]?key|chave)\b(\s*[:=]\s*)([^\s,;]+)"
)


def sanitize_text(value: object, sensitive_values: tuple[str, ...] = ()) -> str:
    """Mascara atribuições e valores sensíveis antes de persistir o log."""
    sanitized = str(value)
    sanitized = SENSITIVE_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        sanitized,
    )
    for secret in sensitive_values:
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    return sanitized


def resolve_log_environment(
    record: logging.LogRecord,
    settings: Settings,
) -> str:
    """Resolve o ambiente sem fixar local quando a execucao vem do Runner."""
    ambiente = getattr(record, "ambiente", None)
    if ambiente:
        return str(ambiente)
    return "runner" if settings.runner_context else "local"


class StructuredJsonFormatter(logging.Formatter):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.sensitive_values = tuple(
            value
            for value in (
                settings.maestro_key,
                os.getenv("BOTCITY_TOKEN", ""),
            )
            if value
        )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                UTC,
            ).isoformat(),
            "level": record.levelname,
            "execution_id": self.settings.execution_id,
            "bot_id": self.settings.bot_id,
            "evento": getattr(record, "evento", "LOG"),
            "aplicacao": getattr(
                record,
                "aplicacao",
                "bot-conferencia-de-lotes-v1",
            ),
            "ambiente": resolve_log_environment(record, self.settings),
            "usuario": getattr(record, "usuario", "sistema"),
            "detalhes": {
                "formulario": getattr(record, "formulario", None),
                "status": getattr(record, "status", None),
                "mensagem": sanitize_text(
                    record.getMessage(),
                    self.sensitive_values,
                ),
            },
        }

        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            payload["detalhes"]["exception"] = sanitize_text(
                self.formatException(record.exc_info),
                self.sensitive_values,
            )
            payload["detalhes"]["exception_type"] = (
                exc_type.__name__ if exc_type else None
            )
            payload["detalhes"]["exception_message"] = sanitize_text(
                exc_value,
                self.sensitive_values,
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
        )


def configure_logging(
    log_file: Path,
    settings: Settings | None = None,
) -> logging.Logger:
    """Cria logger de arquivo e console com data, hora, severidade e mensagem."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    current_settings = settings or Settings.from_env()
    formatter = StructuredJsonFormatter(current_settings)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
