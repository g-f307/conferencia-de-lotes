"""Contratos serializáveis da coleta desktop do Capstone."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StockRecord:
    """Registro exibido e coletado exclusivamente pela interface gráfica."""

    lote_id: str
    produto: str
    quantidade_disponivel: int
    localizacao: str
    status_estoque: str
    atualizado_em: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DesktopCollectionContext:
    """Identificadores fornecidos pelo Dispatcher à task desktop."""

    execution_id: str
    correlation_id: str
    root_task_id: str
    task_id: str
    parent_task_id: str
    trigger_bot: str = "dispatcher-v2"
    expected_items: int | None = None

    def __post_init__(self) -> None:
        required = (
            self.execution_id,
            self.correlation_id,
            self.root_task_id,
            self.task_id,
            self.parent_task_id,
            self.trigger_bot,
        )
        if any(not value.strip() for value in required):
            raise ValueError("identificadores da coleta desktop não podem ser vazios")
        if self.expected_items is not None and self.expected_items < 0:
            raise ValueError("expected_items não pode ser negativo")
