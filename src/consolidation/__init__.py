"""API pública da consolidação determinística do Capstone."""

from .models import (
    STATUS_APROVADO,
    STATUS_DIVERGENCIA,
    STATUS_ERRO_ITEM,
    STATUS_REVISAO,
    FalhaItemConsolidacao,
    RegistroConsolidado,
    ResultadoConsolidacao,
)
from .service import (
    ConsolidationInputError,
    ConsolidationService,
)

__all__ = [
    "STATUS_APROVADO",
    "STATUS_DIVERGENCIA",
    "STATUS_ERRO_ITEM",
    "STATUS_REVISAO",
    "ConsolidationInputError",
    "ConsolidationService",
    "FalhaItemConsolidacao",
    "RegistroConsolidado",
    "ResultadoConsolidacao",
]
