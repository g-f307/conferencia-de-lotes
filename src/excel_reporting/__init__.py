"""Leitura e validacao dos dados utilizados nos relatorios Excel."""

from src.excel_reporting.models import RegistroValidado
from src.excel_reporting.validation_service import (
    CLASSIFICACAO_AMBIGUO,
    CLASSIFICACAO_DIVERGENCIA,
    CLASSIFICACAO_ERRO_ENTRADA,
    CLASSIFICACAO_VALIDO,
    ValidationService,
    validar_registro,
)
from src.excel_reporting.workbook_reader import (
    DAILY_SHEET_PATTERN,
    DEFAULT_WORKBOOK_PATH,
    WorkbookReadResult,
    list_daily_sheet_names,
    read_reference_base,
    read_workbook,
)

__all__ = [
    "CLASSIFICACAO_AMBIGUO",
    "CLASSIFICACAO_DIVERGENCIA",
    "CLASSIFICACAO_ERRO_ENTRADA",
    "CLASSIFICACAO_VALIDO",
    "DAILY_SHEET_PATTERN",
    "DEFAULT_WORKBOOK_PATH",
    "RegistroValidado",
    "ValidationService",
    "WorkbookReadResult",
    "list_daily_sheet_names",
    "read_reference_base",
    "read_workbook",
    "validar_registro",
]
