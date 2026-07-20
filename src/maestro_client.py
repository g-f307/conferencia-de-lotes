"""Adaptador para isolar a integração com o BotCity Maestro."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from src.config import Settings


class MaestroGateway(Protocol):
    """Operações mínimas esperadas do cliente real ou de um mock em testes."""

    def create_datapool_entry(self, datapool_label: str, data: dict[str, str]) -> Any:
        ...

    def has_next(self, datapool_label: str) -> bool:
        ...

    def next(self, datapool_label: str) -> dict[str, str]:
        ...

    def send_error_alert(self, message: str) -> None:
        ...

    def post_artifact(self, name: str, path: Path) -> None:
        ...


class InMemoryMaestroGateway:
    """Gateway local usado quando o Maestro real não está habilitado."""

    def __init__(self) -> None:
        self.entries: dict[str, list[dict[str, str]]] = {}
        self.alerts: list[str] = []
        self.artifacts: list[tuple[str, Path]] = []

    def create_datapool_entry(self, datapool_label: str, data: dict[str, str]) -> None:
        self.entries.setdefault(datapool_label, []).append(dict(data))

    def has_next(self, datapool_label: str) -> bool:
        return bool(self.entries.get(datapool_label))

    def next(self, datapool_label: str) -> dict[str, str]:
        return self.entries.setdefault(datapool_label, []).pop(0)

    def send_error_alert(self, message: str) -> None:
        self.alerts.append(message)

    def post_artifact(self, name: str, path: Path) -> None:
        self.artifacts.append((name, path))


class MaestroClient:
    """Facade usada pelo Dispatcher e pelo núcleo para falar com o Maestro."""

    def __init__(
        self,
        settings: Settings,
        gateway: MaestroGateway | None = None,
    ) -> None:
        self.settings = settings
        self.datapool_label = settings.datapool_label
        self.gateway = gateway or InMemoryMaestroGateway()

    def create_entry(self, data: dict[str, str]) -> None:
        """Publica um item no DataPool configurado."""
        self.gateway.create_datapool_entry(self.datapool_label, data)

    def has_next(self) -> bool:
        """Indica se há item disponível para o Performer."""
        return self.gateway.has_next(self.datapool_label)

    def next(self) -> dict[str, str]:
        """Obtém o próximo item da fila configurada."""
        return self.gateway.next(self.datapool_label)

    def send_error_alert(self, message: str) -> None:
        """Implementa o contrato AlertGateway definido no núcleo."""
        self.gateway.send_error_alert(message)

    def send_start_alert(self) -> None:
        """Emite o alerta inicial exigido pela integração Maestro."""
        self.gateway.send_error_alert("Iniciando auditoria de acessos")

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
