"""Configuração do log local exigido pelo processo."""

import logging
from pathlib import Path


LOGGER_NAME = "auditor_lotes"


def configure_logging(log_file: Path) -> logging.Logger:
    """Cria um logger de arquivo com data, hora, severidade e mensagem."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger
