"""Adaptador para isolar a integração com o BotCity Maestro."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from src.config import Settings
from src.reporting import generate_evidence_pdf
from src.validation import HumanReviewRequired

DATAPOOL_OUTPUT_FIELDS = (
    "resultado_validacao",
    "evidencia",
    "mensagem_resultado",
    "causa_provavel",
    "origem_decisao",
    "confianca_ml",
    "motivo_fallback",
)


@dataclass(frozen=True)
class MaestroTask:
    """Representação estável de uma task, independente do modelo do SDK."""

    task_id: str
    state: str
    parameters: dict[str, object]
    finish_status: str | None = None
    finish_message: str = ""
    activity_label: str = ""
    priority: int | None = None
    predecessor_task_ids: tuple[str, ...] = ()
    timeout_seconds: float | None = None


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

    def mark_business_error(
        self,
        item: Any,
        error: str,
        result: dict[str, str],
    ) -> None:
        ...

    def mark_system_error(
        self,
        item: Any,
        error: str,
        result: dict[str, str],
    ) -> None:
        ...

    def mark_human_review(
        self,
        item: Any,
        review: HumanReviewRequired,
        result: dict[str, str],
    ) -> None:
        ...

    def mark_ml_offline_review(
        self,
        item: Any,
        review: HumanReviewRequired,
        result: dict[str, str],
    ) -> None:
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

    @property
    def current_task_id(self) -> str:
        ...

    def create_task(
        self,
        activity_label: str,
        parameters: dict[str, object],
        *,
        priority: int | None = None,
        predecessor_task_ids: tuple[str, ...] = (),
        timeout_seconds: float | None = None,
    ) -> MaestroTask:
        ...

    def get_task(self, task_id: str) -> MaestroTask:
        ...


class InMemoryMaestroGateway:
    """Gateway local usado quando o Maestro real não está habilitado."""

    def __init__(self, task_id: str = "local-task") -> None:
        self._current_task_id = str(task_id).strip() or "local-task"
        self._task_sequence = 0
        self.tasks: dict[str, MaestroTask] = {
            self._current_task_id: MaestroTask(
                task_id=self._current_task_id,
                state="RUNNING",
                parameters={},
            )
        }
        self.orchestration_events: list[tuple[str, str]] = []
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
        self._apply_outputs(item, result)
        self.done.append((item, result))

    def mark_business_error(
        self,
        item: Any,
        error: str,
        result: dict[str, str],
    ) -> None:
        self._apply_outputs(item, result)
        self.business_errors.append((item, error))

    def mark_system_error(
        self,
        item: Any,
        error: str,
        result: dict[str, str],
    ) -> None:
        self._apply_outputs(item, result)
        self.system_errors.append((item, error))

    def mark_human_review(
        self,
        item: Any,
        review: HumanReviewRequired,
        result: dict[str, str],
    ) -> None:
        self._apply_outputs(item, result)
        self.human_reviews.append((item, review))

    def mark_ml_offline_review(
        self,
        item: Any,
        review: HumanReviewRequired,
        result: dict[str, str],
    ) -> None:
        self._apply_outputs(item, result)
        self.human_reviews.append((item, review))

    @staticmethod
    def _apply_outputs(item: Any, result: Mapping[str, str]) -> None:
        if isinstance(item, dict):
            item.update(
                {
                    field: str(result.get(field) or "")
                    for field in DATAPOOL_OUTPUT_FIELDS
                }
            )

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
        self.orchestration_events.append(("finish_task", self._current_task_id))
        current = self.tasks[self._current_task_id]
        self.tasks[self._current_task_id] = replace(
            current,
            state="FINISHED",
            finish_status=status,
            finish_message=message,
        )

    @property
    def current_task_id(self) -> str:
        return self._current_task_id

    def create_task(
        self,
        activity_label: str,
        parameters: dict[str, object],
        *,
        priority: int | None = None,
        predecessor_task_ids: tuple[str, ...] = (),
        timeout_seconds: float | None = None,
    ) -> MaestroTask:
        self._task_sequence += 1
        task_id = f"local-child-{self._task_sequence}"
        task = MaestroTask(
            task_id=task_id,
            state="START",
            parameters=dict(parameters),
            activity_label=activity_label,
            priority=priority,
            predecessor_task_ids=tuple(predecessor_task_ids),
            timeout_seconds=timeout_seconds,
        )
        self.tasks[task_id] = task
        self.orchestration_events.append(("create_task", task_id))
        return task

    def get_task(self, task_id: str) -> MaestroTask:
        try:
            return self.tasks[str(task_id)]
        except KeyError as exc:
            raise ValueError(f"Task inexistente: {task_id}") from exc

    def activate_task(self, task_id: str) -> None:
        """Seleciona uma task criada para simular outro Runner em testes."""
        task = self.get_task(task_id)
        self._current_task_id = task.task_id
        self.tasks[task.task_id] = replace(task, state="RUNNING")


@dataclass(frozen=True)
class DataPoolWorkItem(Mapping[str, Any]):
    """Item entregue ao Performer mantendo a referência do DataPoolEntry real."""

    entry: Any
    values: Mapping[str, Any]

    @classmethod
    def from_entry(cls, entry: Any) -> DataPoolWorkItem:
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
    def from_settings(cls, settings: Settings) -> BotCityMaestroGateway:
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
            return self.sdk.task_id
        return None

    def _require_task_id(self) -> str | int:
        if not self._is_valid_task_id(self.task_id):
            raise RuntimeError(
                "MAESTRO_TASK_ID ausente ou inválido para operação dependente de task"
            )
        return self.task_id

    @property
    def current_task_id(self) -> str:
        return str(self._require_task_id())

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

    @staticmethod
    def _apply_outputs(entry: Any, result: Mapping[str, str]) -> None:
        values = getattr(entry, "values", None)
        if not isinstance(values, dict):
            raise TypeError("DataPoolEntry recebido sem values mutável")
        values.update(
            {
                field: str(result.get(field) or "")
                for field in DATAPOOL_OUTPUT_FIELDS
            }
        )

    def mark_done(self, item: Any, result: dict[str, str]) -> None:
        entry = self._entry_from_item(item)
        self._apply_outputs(entry, result)
        entry.report_done(finish_message="Lote processado com sucesso")

    def mark_business_error(
        self,
        item: Any,
        error: str,
        result: dict[str, str],
    ) -> None:
        entry = self._entry_from_item(item)
        self._apply_outputs(entry, result)
        entry.report_error(
            error_type=self.error_type.BUSINESS,
            finish_message=error,
        )

    def mark_system_error(
        self,
        item: Any,
        error: str,
        result: dict[str, str],
    ) -> None:
        entry = self._entry_from_item(item)
        self._apply_outputs(entry, result)
        entry.report_error(
            error_type=self.error_type.SYSTEM,
            finish_message=error,
        )

    def mark_human_review(
        self,
        item: Any,
        review: HumanReviewRequired,
        result: dict[str, str],
    ) -> None:
        entry = self._entry_from_item(item)
        self._apply_outputs(entry, result)
        entry.report_error(
            error_type=self.error_type.BUSINESS,
            finish_message=review.reason,
        )

    def mark_ml_offline_review(
        self,
        item: Any,
        review: HumanReviewRequired,
        result: dict[str, str],
    ) -> None:
        """Persiste o fallback como revisão, sem classificá-lo como erro."""
        entry = self._entry_from_item(item)
        self._apply_outputs(entry, result)
        entry.report_done(finish_message=review.reason)

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

    def create_task(
        self,
        activity_label: str,
        parameters: dict[str, object],
        *,
        priority: int | None = None,
        predecessor_task_ids: tuple[str, ...] = (),
        timeout_seconds: float | None = None,
    ) -> MaestroTask:
        legacy_parameters = dict(parameters)
        if priority is not None or predecessor_task_ids or timeout_seconds is not None:
            legacy_parameters["scheduling"] = {
                "priority": priority,
                "predecessor_task_ids": list(predecessor_task_ids),
                "timeout_seconds": timeout_seconds,
            }
        task = self.sdk.create_task(activity_label, legacy_parameters)
        return replace(
            self._to_task(task),
            priority=priority,
            predecessor_task_ids=tuple(predecessor_task_ids),
            timeout_seconds=timeout_seconds,
        )

    def get_task(self, task_id: str) -> MaestroTask:
        return self._to_task(self.sdk.get_task(str(task_id)))

    @staticmethod
    def _to_task(task: Any) -> MaestroTask:
        def enum_value(value: Any) -> str | None:
            if value is None:
                return None
            return str(getattr(value, "value", value))

        return MaestroTask(
            task_id=str(getattr(task, "id", "")),
            state=enum_value(getattr(task, "state", "")) or "",
            parameters=dict(getattr(task, "parameters", None) or {}),
            finish_status=enum_value(getattr(task, "finish_status", None)),
            finish_message=str(getattr(task, "finish_message", "") or ""),
            activity_label=str(getattr(task, "activity_label", "") or ""),
            priority=getattr(task, "priority", None),
            predecessor_task_ids=tuple(
                getattr(task, "predecessor_task_ids", None) or ()
            ),
            timeout_seconds=getattr(task, "timeout_seconds", None),
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
        return InMemoryMaestroGateway(
            settings.maestro_task_id or settings.execution_id
        )

    @property
    def current_task_id(self) -> str:
        """Identificador da task que está executando o bot atual."""
        return self.gateway.current_task_id

    def create_task(
        self,
        activity_label: str,
        parameters: dict[str, object],
        *,
        priority: int | None = None,
        predecessor_task_ids: tuple[str, ...] = (),
        timeout_seconds: float | None = None,
    ) -> MaestroTask:
        """Agenda a próxima atividade preservando os parâmetros de correlação."""
        return self.gateway.create_task(
            activity_label,
            parameters,
            priority=priority,
            predecessor_task_ids=predecessor_task_ids,
            timeout_seconds=timeout_seconds,
        )

    def get_task(self, task_id: str) -> MaestroTask:
        """Consulta uma task sem expor o modelo específico do SDK."""
        return self.gateway.get_task(task_id)

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

    def mark_business_error(
        self,
        item: Any,
        error: str,
        result: dict[str, str],
    ) -> None:
        """Finaliza um item com erro de negócio."""
        self.gateway.mark_business_error(item, error, result)

    def mark_system_error(
        self,
        item: Any,
        error: str,
        result: dict[str, str],
    ) -> None:
        """Finaliza um item com erro técnico/sistêmico."""
        self.gateway.mark_system_error(item, error, result)

    def mark_human_review(
        self,
        item: Any,
        review: HumanReviewRequired,
        result: dict[str, str],
    ) -> None:
        """Finaliza um item separado para revisão humana."""
        self.gateway.mark_human_review(item, review, result)

    def mark_ml_offline_review(
        self,
        item: Any,
        review: HumanReviewRequired,
        result: dict[str, str],
    ) -> None:
        """Finaliza fallback de ML sem reportar erro técnico ou de negócio."""
        self.gateway.mark_ml_offline_review(item, review, result)

    def send_error_alert(self, message: str) -> None:
        """Implementa o contrato AlertGateway definido no núcleo."""
        self.gateway.send_error_alert(message)

    def send_info_alert(self, message: str) -> None:
        """Publica uma notificação informativa vinculada à task atual."""
        self.gateway.send_info_alert(message)

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

    def post_evidence_report(
        self,
        summary: dict[str, Any],
        metadata: dict[str, Any],
        report_dir: Path | None = None,
        evidence_path: Path | None = None,
        artifact_name: str = "relatorio_evidencias.pdf",
    ) -> Path:
        """Gera o relatorio PDF e o publica como artefato da task."""
        destination = report_dir or self.settings.report_dir
        artifact_path = generate_evidence_pdf(
            summary,
            destination / artifact_name,
            metadata,
            evidence_path,
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
