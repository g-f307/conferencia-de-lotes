"""Contratos de execução do bot independente de ML."""

from __future__ import annotations

from dataclasses import dataclass


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} deve ser informado")
    return normalized


@dataclass(frozen=True)
class MLBotContext:
    """Identificadores propagados sem alteração pela cadeia de bots."""

    execution_id: str
    correlation_id: str
    root_task_id: str
    task_id: str
    parent_task_id: str | None = None
    predecessor_task_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "execution_id",
            "correlation_id",
            "root_task_id",
            "task_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )

        parent = str(self.parent_task_id or "").strip() or None
        predecessors = tuple(
            dict.fromkeys(
                _required_text(task_id, "predecessor_task_ids")
                for task_id in self.predecessor_task_ids
            )
        )
        object.__setattr__(self, "parent_task_id", parent)
        object.__setattr__(self, "predecessor_task_ids", predecessors)
