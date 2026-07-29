"""Modelos compartilhados para padronizar o resultado da execução."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExecutionResult:
    """Resumo serializável produzido pelo ciclo principal do bot."""

    status: str = "SUCCESS"
    message: str = ""
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0
    ambiguous_items: int = 0
    approved_items: int = 0
    rejected_items: int = 0
    divergence_items: int = 0
    technical_errors: int = 0
    evidences: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None

    def complete(self) -> "ExecutionResult":
        """Fecha o resultado e deriva o estado a partir dos contadores."""
        self.finished_at = utc_now()
        if self.status == "FAILED":
            return self
        self.status = (
            "PARTIALLY_COMPLETED"
            if self.failed_items or self.ambiguous_items
            else "SUCCESS"
        )
        return self

    def fail(self, message: str) -> "ExecutionResult":
        """Marca uma falha fatal anterior ao processamento dos itens."""
        self.status = "FAILED"
        self.message = message
        self.finished_at = utc_now()
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
