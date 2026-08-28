"""Contratos serializáveis da consolidação determinística do Capstone."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any

from src.desktop_stock.models import StockRecord
from src.excel_reporting.models import RegistroValidado
from src.supplier_portal import SupplierOrder

STATUS_APROVADO = "APROVADO"
STATUS_DIVERGENCIA = "DIVERGENCIA"
STATUS_REVISAO = "PENDENTE_REVISAO"
STATUS_ERRO_ITEM = "ERRO_ITEM"


@dataclass(frozen=True)
class RegistroConsolidado:
    """Visão auditável de um lote após cruzamento das fontes controladas."""

    lote_id: str
    estoque: StockRecord | None
    pedido: SupplierOrder | None
    validacao: RegistroValidado | None
    status_operacional: str
    classificacao: str
    motivo: str
    regras_violadas: tuple[str, ...]
    regra_aplicada: str
    verificacoes_consolidacao: tuple[str, ...]
    origens_consultadas: tuple[str, ...]
    fontes_ausentes: tuple[str, ...]
    modo_degradado: bool
    origem_campos: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "regras_violadas", tuple(self.regras_violadas))
        object.__setattr__(
            self,
            "verificacoes_consolidacao",
            tuple(self.verificacoes_consolidacao),
        )
        object.__setattr__(self, "origens_consultadas", tuple(self.origens_consultadas))
        object.__setattr__(self, "fontes_ausentes", tuple(self.fontes_ausentes))
        object.__setattr__(
            self,
            "origem_campos",
            MappingProxyType(
                {key: tuple(value) for key, value in self.origem_campos.items()}
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lote_id": self.lote_id,
            "pedido_id": self.pedido.pedido_id if self.pedido else None,
            "quantidade_disponivel": (
                self.estoque.quantidade_disponivel if self.estoque else None
            ),
            "quantidade_solicitada": (
                self.pedido.quantidade_solicitada if self.pedido else None
            ),
            "estoque": self.estoque.to_dict() if self.estoque else None,
            "pedido": self.pedido.to_dict() if self.pedido else None,
            "validacao": self.validacao.to_dict() if self.validacao else None,
            "status_operacional": self.status_operacional,
            "classificacao": self.classificacao,
            "motivo": self.motivo,
            "regras_violadas": list(self.regras_violadas),
            "regra_aplicada": self.regra_aplicada,
            "verificacoes_consolidacao": list(self.verificacoes_consolidacao),
            "origens_consultadas": list(self.origens_consultadas),
            "fontes_ausentes": list(self.fontes_ausentes),
            "modo_degradado": self.modo_degradado,
            "origem_campos": {
                key: list(value) for key, value in self.origem_campos.items()
            },
        }


@dataclass(frozen=True)
class FalhaItemConsolidacao:
    """Falha isolada que não impede a consolidação dos demais lotes."""

    fonte: str
    indice: int
    lote_id: str | None
    codigo: str
    mensagem: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResultadoConsolidacao:
    """Envelope consumível pelo classificador, relatório e alertas."""

    status: str
    registros: tuple[RegistroConsolidado, ...]
    falhas_itens: tuple[FalhaItemConsolidacao, ...]
    status_fontes: Mapping[str, str]
    modo_degradado: bool
    ml_consultado: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "registros", tuple(self.registros))
        object.__setattr__(self, "falhas_itens", tuple(self.falhas_itens))
        object.__setattr__(
            self,
            "status_fontes",
            MappingProxyType(dict(self.status_fontes)),
        )

    def to_dict(self) -> dict[str, Any]:
        review_items = sum(
            item.status_operacional == STATUS_REVISAO for item in self.registros
        )
        failed_items = len(self.falhas_itens) + sum(
            item.status_operacional == STATUS_ERRO_ITEM for item in self.registros
        )
        return {
            "schema_version": "1.0",
            "status": self.status,
            "modo_degradado": self.modo_degradado,
            "ml_consultado": self.ml_consultado,
            "source_statuses": dict(self.status_fontes),
            "payload": {
                "records": [item.to_dict() for item in self.registros],
                "item_failures": [item.to_dict() for item in self.falhas_itens],
                "total_items": len(self.registros) + len(self.falhas_itens),
                "processed_items": len(self.registros),
                "failed_items": failed_items,
                "review_items": review_items,
            },
        }
