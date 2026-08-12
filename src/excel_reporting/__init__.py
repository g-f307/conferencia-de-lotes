"""Modelos e validações isolados para a futura geração de relatórios Excel."""

from src.excel_reporting.models import RegistroValidado
from src.excel_reporting.validation_service import (
    CLASSIFICACAO_AMBIGUO,
    CLASSIFICACAO_DIVERGENCIA,
    CLASSIFICACAO_ERRO_ENTRADA,
    CLASSIFICACAO_VALIDO,
    ValidationService,
    validar_registro,
)

__all__ = [
    "CLASSIFICACAO_AMBIGUO",
    "CLASSIFICACAO_DIVERGENCIA",
    "CLASSIFICACAO_ERRO_ENTRADA",
    "CLASSIFICACAO_VALIDO",
    "RegistroValidado",
    "ValidationService",
    "validar_registro",
]
