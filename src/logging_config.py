"""Configuração do log local e console exigido pelo processo."""

import logging
import sys
from pathlib import Path


LOGGER_NAME = "auditor_lotes"


def configure_logging(log_file: Path) -> logging.Logger:
    """Cria logger de arquivo e console com data, hora, severidade e mensagem."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
