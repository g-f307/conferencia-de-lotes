"""Adaptador para isolar a integração com o BotCity Maestro."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from src.config import Settings
from src.validation import HumanReviewRequired


class MaestroGateway(Protocol):
    """Operações mínimas esperadas do cliente real ou de um mock em testes."""

    def create_datapool_entry(self, datapool_label: str, data: dict[str, str]) -> Any:
        ...

    def has_next(self, datapool_label: str) -> bool:
        ...

    def next(self, datapool_label: str) -> dict[str, str] | None:
        ...

    def mark_done(self, item: Any, result: dict[str, str]) -> None:
        ...

    def mark_business_error(self, item: Any, error: str) -> None:
        ...

    def mark_system_error(self, item: Any, error: str) -> None:
        ...

    def mark_human_review(self, item: Any, review: HumanReviewRequired) -> None:
        ...

    def send_info_alert(self, message: str) -> None:
        ...

    def send_error_alert(self, message: str) -> None:
        ...

    def post_artifact(self, name: str, path: Path) -> None:
        ...

    def finish_task(
        self,
        status: str,
        message: str,
        total_items: int,
        processed_items: int,
        failed_items: int,
    ) -> None:
        ...


class InMemoryMaestroGateway:
    """Gateway local usado quando o Maestro real não está habilitado."""

    def __init__(self) -> None:
        self.entries: dict[str, list[dict[str, str]]] = {}
        self.alerts: list[str] = []
        self.info_alerts: list[str] = []
        self.artifacts: list[tuple[str, Path]] = []
        self.done: list[tuple[Any, dict[str, str]]] = []
        self.business_errors: list[tuple[Any, str]] = []
        self.system_errors: list[tuple[Any, str]] = []
        self.human_reviews: list[tuple[Any, HumanReviewRequired]] = []
        self.finished_tasks: list[tuple[str, str, int, int, int]] = []

    def create_datapool_entry(self, datapool_label: str, data: dict[str, str]) -> None:
        self.entries.setdefault(datapool_label, []).append(dict(data))

    def has_next(self, datapool_label: str) -> bool:
        return bool(self.entries.get(datapool_label))

    def next(self, datapool_label: str) -> dict[str, str] | None:
        return self.entries.setdefault(datapool_label, []).pop(0)

    def mark_done(self, item: Any, result: dict[str, str]) -> None:
        self.done.append((item, result))

    def mark_business_error(self, item: Any, error: str) -> None:
        self.business_errors.append((item, error))

    def mark_system_error(self, item: Any, error: str) -> None:
        self.system_errors.append((item, error))

    def mark_human_review(self, item: Any, review: HumanReviewRequired) -> None:
        self.human_reviews.append((item, review))

    def send_info_alert(self, message: str) -> None:
        self.info_alerts.append(message)

    def send_error_alert(self, message: str) -> None:
        self.alerts.append(message)

    def post_artifact(self, name: str, path: Path) -> None:
        self.artifacts.append((name, path))

    def finish_task(
        self,
        status: str,
        message: str,
        total_items: int,
        processed_items: int,
        failed_items: int,
    ) -> None:
        self.finished_tasks.append(
            (status, message, total_items, processed_items, failed_items)
        )


@dataclass(frozen=True)
class DataPoolWorkItem(Mapping[str, Any]):
    """Item entregue ao Performer mantendo a referência do DataPoolEntry real."""

    entry: Any
    values: Mapping[str, Any]

    @classmethod
    def from_entry(cls, entry: Any) -> "DataPoolWorkItem":
        values = getattr(entry, "values", None)
        if values is None:
            raise TypeError("DataPoolEntry recebido sem atributo values")
        return cls(entry=entry, values=values)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


class BotCityMaestroGateway:
    """Gateway real para operações do BotCity Maestro SDK."""

    def __init__(
        self,
        sdk: Any,
        datapool_entry_cls: type,
        error_type: Any,
        alert_type: Any,
        finish_status_type: Any,
        task_id: str | int | None = None,
    ) -> None:
        self.sdk = sdk
        self.datapool_entry_cls = datapool_entry_cls
        self.error_type = error_type
        self.alert_type = alert_type
        self.finish_status_type = finish_status_type
        self.task_id = self._resolve_task_id(task_id if task_id is not None else getattr(sdk, "task_id", None))

    @classmethod
    def from_settings(cls, settings: Settings) -> "BotCityMaestroGateway":
        """Constrói o gateway real com as credenciais técnicas do Maestro."""
        try:
            from botcity.maestro import (
                AlertType,
                AutomationTaskFinishStatus,
                BotMaestroSDK,
                DataPoolEntry,
                ErrorType,
            )
        except ImportError as exc:
            raise RuntimeError(
                "botcity-maestro-sdk deve estar instalado quando MAESTRO_ENABLED=true"
            ) from exc

        sdk = BotMaestroSDK.from_sys_args()
        if not cls._is_valid_task_id(getattr(sdk, "task_id", None)):
            sdk = BotMaestroSDK(
                server=settings.maestro_server,
                login=settings.maestro_login,
                key=settings.maestro_key,
            )
            sdk.login()
        task_id = settings.maestro_task_id or os.getenv("MAESTRO_TASK_ID", "")
        return cls(
            sdk,
            DataPoolEntry,
            ErrorType,
            AlertType,
            AutomationTaskFinishStatus,
            task_id=task_id,
        )

    @staticmethod
    def _is_valid_task_id(task_id: Any) -> bool:
        return str(task_id or "").strip() not in {"", "0"}

    def _resolve_task_id(self, configured_task_id: Any) -> str | int | None:
        if self._is_valid_task_id(configured_task_id):
            return configured_task_id
        if self._is_valid_task_id(getattr(self.sdk, "task_id", None)):
            return getattr(self.sdk, "task_id")
        return None

    def _require_task_id(self) -> str | int:
        if not self._is_valid_task_id(self.task_id):
            raise RuntimeError(
                "MAESTRO_TASK_ID ausente ou inválido para operação dependente de task"
            )
        return self.task_id

    def _datapool(self, datapool_label: str) -> Any:
        return self.sdk.get_datapool(datapool_label)

    def create_datapool_entry(self, datapool_label: str, data: dict[str, str]) -> Any:
        entry = self.datapool_entry_cls(values=data)
        return self._datapool(datapool_label).create_entry(entry)

    def has_next(self, datapool_label: str) -> bool:
        return self._datapool(datapool_label).has_next()

    def next(self, datapool_label: str) -> DataPoolWorkItem | None:
        entry = self._datapool(datapool_label).next(task_id=self._require_task_id())
        if entry is None:
            return None
        return DataPoolWorkItem.from_entry(entry)

    def _entry_from_item(self, item: Any) -> Any:
        return item.entry if isinstance(item, DataPoolWorkItem) else item

    def mark_done(self, item: Any, result: dict[str, str]) -> None:
        self._entry_from_item(item).report_done(finish_message="Lote processado com sucesso")

    def mark_business_error(self, item: Any, error: str) -> None:
        self._entry_from_item(item).report_error(
            error_type=self.error_type.BUSINESS,
            finish_message=error,
        )

    def mark_system_error(self, item: Any, error: str) -> None:
        self._entry_from_item(item).report_error(
            error_type=self.error_type.SYSTEM,
            finish_message=error,
        )

    def mark_human_review(self, item: Any, review: HumanReviewRequired) -> None:
        self._entry_from_item(item).report_error(
            error_type=self.error_type.BUSINESS,
            finish_message=review.reason,
        )

    def send_info_alert(self, message: str) -> None:
        self.sdk.alert(
            task_id=self._require_task_id(),
            title="Auditoria de lotes",
            message=message,
            alert_type=self.alert_type.INFO,
        )

    def send_error_alert(self, message: str) -> None:
        self.sdk.alert(
            task_id=self._require_task_id(),
            title="Auditoria de lotes",
            message=message,
            alert_type=self.alert_type.ERROR,
        )

    def post_artifact(self, name: str, path: Path) -> None:
        self.sdk.post_artifact(self._require_task_id(), name, str(path))

    def finish_task(
        self,
        status: str,
        message: str,
        total_items: int,
        processed_items: int,
        failed_items: int,
    ) -> None:
        finish_status = getattr(self.finish_status_type, status)
        self.sdk.finish_task(
            self._require_task_id(),
            finish_status,
            message=message,
            total_items=total_items,
            processed_items=processed_items,
            failed_items=failed_items,
        )


class MaestroClient:
    """Facade usada pelo Dispatcher e pelo núcleo para falar com o Maestro."""

    def __init__(
        self,
        settings: Settings,
        gateway: MaestroGateway | None = None,
        real_gateway_factory: Callable[[Settings], MaestroGateway] | None = None,
    ) -> None:
        self.settings = settings
        self.datapool_label = settings.datapool_label
        self.gateway = gateway or self._build_gateway(settings, real_gateway_factory)

    def _build_gateway(
        self,
        settings: Settings,
        real_gateway_factory: Callable[[Settings], MaestroGateway] | None,
    ) -> MaestroGateway:
        if settings.maestro_enabled:
            factory = real_gateway_factory or BotCityMaestroGateway.from_settings
            return factory(settings)
        return InMemoryMaestroGateway()

    def create_entry(self, data: dict[str, str]) -> None:
        """Publica um item no DataPool configurado."""
        self.gateway.create_datapool_entry(self.datapool_label, data)

    def has_next(self) -> bool:
        """Indica se há item disponível para o Performer."""
        return self.gateway.has_next(self.datapool_label)

    def next(self) -> dict[str, str] | None:
        """Obtém o próximo item da fila configurada."""
        return self.gateway.next(self.datapool_label)

    def mark_done(self, item: Any, result: dict[str, str]) -> None:
        """Finaliza um item processado com sucesso."""
        self.gateway.mark_done(item, result)

    def mark_business_error(self, item: Any, error: str) -> None:
        """Finaliza um item com erro de negócio."""
        self.gateway.mark_business_error(item, error)

    def mark_system_error(self, item: Any, error: str) -> None:
        """Finaliza um item com erro técnico/sistêmico."""
        self.gateway.mark_system_error(item, error)

    def mark_human_review(self, item: Any, review: HumanReviewRequired) -> None:
        """Finaliza um item separado para revisão humana."""
        self.gateway.mark_human_review(item, review)

    def send_error_alert(self, message: str) -> None:
        """Implementa o contrato AlertGateway definido no núcleo."""
        self.gateway.send_error_alert(message)

    def send_start_alert(self) -> None:
        """Emite o alerta informativo inicial exigido pela integração Maestro."""
        self.gateway.send_info_alert("Iniciando auditoria de acessos")

    def post_summary_artifact(
        self,
        summary: dict[str, Any],
        report_dir: Path | None = None,
        artifact_name: str = "resumo_execucao.json",
    ) -> Path:
        """Salva um resumo JSON local e publica o arquivo como artefato."""
        destination = report_dir or self.settings.report_dir
        destination.mkdir(parents=True, exist_ok=True)
        artifact_path = destination / artifact_name
        artifact_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.gateway.post_artifact(artifact_name, artifact_path)
        return artifact_path

    def finish_task(
        self,
        status: str,
        message: str,
        total_items: int,
        processed_items: int,
        failed_items: int,
    ) -> None:
        """Finaliza a task do Maestro com contadores consolidados."""
        self.gateway.finish_task(
            status,
            message,
            total_items,
            processed_items,
            failed_items,
        )
