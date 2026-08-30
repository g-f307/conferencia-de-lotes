"""Smart Office adapter with no direct dependency on a vendor SDK."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from src.maestro_client import MaestroTask


class SmartOfficeClient(Protocol):
    """Minimum client contract required by the orchestration layer."""

    @property
    def current_task_id(self) -> str: ...

    def create_task(
        self,
        activity_label: str,
        parameters: Mapping[str, object],
        *,
        priority: int | None = None,
        predecessor_task_ids: Sequence[str] = (),
        timeout_seconds: float | None = None,
    ) -> object: ...

    def get_task(self, task_id: str) -> object: ...

    def finish_task(
        self,
        status: str,
        message: str,
        total_items: int,
        processed_items: int,
        failed_items: int,
    ) -> None: ...


class SmartOfficeGatewayAdapter:
    """Translate a Smart Office client to the repository gateway contract."""

    def __init__(self, client: SmartOfficeClient) -> None:
        self._client = client

    @property
    def current_task_id(self) -> str:
        task_id = str(self._client.current_task_id).strip()
        if not task_id:
            raise ValueError("Smart Office nao informou a task atual")
        return task_id

    def create_task(
        self,
        activity_label: str,
        parameters: Mapping[str, object],
        *,
        priority: int | None = None,
        predecessor_task_ids: Sequence[str] = (),
        timeout_seconds: float | None = None,
    ) -> MaestroTask:
        task = self._client.create_task(
            activity_label,
            dict(parameters),
            priority=priority,
            predecessor_task_ids=tuple(predecessor_task_ids),
            timeout_seconds=timeout_seconds,
        )
        return self._to_task(
            task,
            priority=priority,
            predecessor_task_ids=predecessor_task_ids,
            timeout_seconds=timeout_seconds,
        )

    def get_task(self, task_id: str) -> MaestroTask:
        return self._to_task(self._client.get_task(task_id))

    def finish_task(
        self,
        status: str,
        message: str,
        total_items: int,
        processed_items: int,
        failed_items: int,
    ) -> None:
        self._client.finish_task(
            status, message, total_items, processed_items, failed_items
        )

    @staticmethod
    def _to_task(
        task: object,
        *,
        priority: int | None = None,
        predecessor_task_ids: Sequence[str] = (),
        timeout_seconds: float | None = None,
    ) -> MaestroTask:
        task_id = getattr(task, "task_id", None) or getattr(task, "id", None)
        if task_id is None:
            raise ValueError("Resposta do Smart Office sem identificador de task")
        parameters = getattr(task, "parameters", {}) or {}
        return MaestroTask(
            task_id=str(task_id),
            activity_label=str(getattr(task, "activity_label", "")),
            state=str(getattr(task, "state", "CREATED")),
            parameters=dict(parameters),
            finish_status=getattr(task, "finish_status", None),
            finish_message=str(
                getattr(task, "finish_message", getattr(task, "message", ""))
            ),
            priority=getattr(task, "priority", priority),
            predecessor_task_ids=tuple(
                getattr(task, "predecessor_task_ids", predecessor_task_ids) or ()
            ),
            timeout_seconds=getattr(task, "timeout_seconds", timeout_seconds),
        )


__all__ = ["SmartOfficeClient", "SmartOfficeGatewayAdapter"]
