"""Espera limitada por uma task predecessora do BotCity Maestro."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from src.maestro_client import MaestroTask

SUCCESS_FINISH_STATUSES = frozenset({"SUCCESS", "PARTIALLY_COMPLETED"})


class TaskLookup(Protocol):
    def get_task(self, task_id: str) -> MaestroTask: ...


class PredecessorError(RuntimeError):
    """Falha terminal que impede a execução da etapa dependente."""


class PredecessorFailedError(PredecessorError):
    pass


class PredecessorTimeoutError(PredecessorError):
    pass


def wait_for_predecessor(
    gateway: TaskLookup,
    predecessor_task_id: str,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> MaestroTask:
    """Aguarda sucesso terminal sem permitir espera indefinida."""
    task_id = str(predecessor_task_id).strip()
    if not task_id:
        raise ValueError("predecessor_task_id deve ser informado")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds deve ser maior que zero")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds deve ser maior que zero")

    deadline = monotonic() + timeout_seconds
    while True:
        task = gateway.get_task(task_id)
        state = task.state.upper()
        finish_status = (task.finish_status or "").upper()

        if state == "FINISHED":
            if finish_status in SUCCESS_FINISH_STATUSES:
                return task
            detail = task.finish_message or finish_status or "status ausente"
            raise PredecessorFailedError(
                f"Task predecessora {task_id} terminou sem sucesso: {detail}"
            )
        if state == "CANCELED":
            raise PredecessorFailedError(
                f"Task predecessora {task_id} foi cancelada"
            )

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise PredecessorTimeoutError(
                f"Timeout ao aguardar a task predecessora {task_id} "
                f"após {timeout_seconds:g}s"
            )
        sleep(min(poll_interval_seconds, remaining))
