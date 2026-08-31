"""Harness local dos seis bots para as sabotagens controladas do Capstone."""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from src.alerts import CanalLogLocal, SistemaAlertas
from src.capstone_orchestrator import (
    CAPSTONE_BOT_LABELS,
    CapstoneContext,
    CapstoneOrchestrationSettings,
    CapstoneOrchestrator,
    CapstoneStage,
    PipelineManifest,
)
from src.capstone_reporting import CapstoneReportResult, CapstoneReportService
from src.classificador_divergencia import (
    ClassificadorDivergencia,
    PredicaoCausa,
)
from src.consolidation.main import run as run_consolidation
from src.dead_letter import DeadLetterWriter
from src.desktop_stock import DesktopCollectionContext, DesktopStockCollector
from src.excel_reporting import RegistroValidado, ValidationService
from src.logging_config import configure_logging, sanitize_text
from src.maestro_client import InMemoryMaestroGateway
from src.ml_audit import MLDecisionRecorder
from src.ml_bot import MLBotContext, MLBotService, write_ml_bot_result
from src.migration_control import CoexistenceCoordinator, ExecutionPermit
from src.orchestrator import StageResult
from src.reference_base import (
    ReferenceBaseService,
    ReferenceInfrastructureError,
    ReferenceLookupResult,
    ReferenceLookupStatus,
)
from src.retry_policy import LinearRetryPolicy
from src.supplier_portal import (
    SupplierOrder,
    SupplierPortalCollector,
    SupplierPortalConfig,
    SupplierSessionResult,
)
from src.wait_for_predecessor import wait_for_predecessor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPLIER_PORTAL_PATH = PROJECT_ROOT / "web" / "supplier-portal" / "index.html"
CONTROLLED_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class CrisisScenario(StrEnum):
    REFERENCE_UNAVAILABLE = "base_referencia_indisponivel"
    ML_UNAVAILABLE = "servico_ml_indisponivel"
    DEPENDENCY_TIMEOUT = "dependencia_timeout"
    DEPENDENCY_CANCELED = "dependencia_cancelada"
    DEPENDENCY_FAILURE = "timeout_cancelamento_dependencia"
    NOTIFICATION_FAILURE = "falha_canal_notificacao"
    CONCURRENCY = "concorrencia_official_shadow"
    IRRECOVERABLE_DATA = "dado_irrecuperavel"
    NOMINAL = "pipeline_nominal"


SIX_REQUIRED_SCENARIOS = (
    CrisisScenario.REFERENCE_UNAVAILABLE,
    CrisisScenario.ML_UNAVAILABLE,
    CrisisScenario.DEPENDENCY_FAILURE,
    CrisisScenario.NOTIFICATION_FAILURE,
    CrisisScenario.CONCURRENCY,
    CrisisScenario.IRRECOVERABLE_DATA,
)


def synthetic_items() -> list[dict[str, object]]:
    products = ("Monitor", "Teclado", "Mouse", "Notebook")
    return [
        {
            "lote_id": f"L{index:03d}",
            "produto": product,
            "linha": "Linha controlada",
            "turno": "Manha",
            "status": "APROVADO",
            "responsavel": "Papel local",
            "data": "31/08/2026",
            "observacao": "massa sintetica",
        }
        for index, product in enumerate(products, start=1)
    ]


class ControlledDesktopDriver:
    """Expõe somente o texto visual e uma captura sintética não sensível."""

    def __init__(self) -> None:
        self.closed = False

    def wait_until_ready(self, timeout_seconds: float) -> None:
        assert timeout_seconds > 0

    def search(self, query: str, timeout_seconds: float) -> None:
        assert query == "*"
        assert timeout_seconds > 0

    def read_visible_records(self, timeout_seconds: float) -> str:
        assert timeout_seconds > 0
        return "\n".join(
            (
                "lote_id\tproduto\tquantidade_disponivel\tlocalizacao\tstatus_estoque\tatualizado_em",
                "L001\tMonitor\t25\tA-01\tDISPONIVEL\t2026-08-31T12:00:00Z",
                "L002\tTeclado\t20\tA-02\tBAIXO\t2026-08-31T12:00:00Z",
                "L003\tMouse\t50\tA-03\tDISPONIVEL\t2026-08-31T12:00:00Z",
                "L004\tNotebook\t8\tA-04\tDISPONIVEL\t2026-08-31T12:00:00Z",
            )
        )

    def capture_evidence(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(CONTROLLED_PNG)
        return destination

    def close(self) -> None:
        self.closed = True


class ControlledSupplierSession:
    """Simula somente a fronteira visual com os dados do portal versionado."""

    def __init__(self, evidence_path: Path) -> None:
        self.evidence_path = evidence_path

    def collect(self) -> SupplierSessionResult:
        orders = (
            SupplierOrder("PED-1001", "L001", "Alfa Componentes", "Monitor", 20, "CONFIRMADO", "28/08/2026"),
            SupplierOrder("PED-1002", "L002", "Beta Tecnologia", "Teclado", 35, "EM_TRANSITO", "29/08/2026"),
            SupplierOrder("PED-1003", "L003", "Gama Suprimentos", "Mouse", 50, "CONFIRMADO", "30/08/2026"),
            SupplierOrder("PED-1004", "L004", "Delta Equipamentos", "Notebook", 8, "PENDENTE", "31/08/2026"),
        )
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_path.write_bytes(CONTROLLED_PNG)
        return SupplierSessionResult(orders, self.evidence_path)


class OfflineReferenceGateway:
    def __init__(self) -> None:
        self.calls = 0

    def contains(self, lote_id: str, *, timeout_seconds: float) -> bool:
        del lote_id, timeout_seconds
        self.calls += 1
        raise ReferenceInfrastructureError("base local indisponivel")


class SelectiveReferenceGateway:
    def __init__(self, invalid_lote_id: str) -> None:
        self.invalid_lote_id = invalid_lote_id
        self.calls: dict[str, int] = {}

    def contains(self, lote_id: str, *, timeout_seconds: float) -> bool:
        del timeout_seconds
        self.calls[lote_id] = self.calls.get(lote_id, 0) + 1
        if lote_id == self.invalid_lote_id:
            return {"invalid": True}  # type: ignore[return-value]
        return True


class ReferenceAlertSpy:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_error_alert(self, message: str) -> None:
        self.messages.append(sanitize_text(message))


class ControlledMLProvider:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.calls = 0

    def classificar(self, observacao: str, timeout_seconds: float) -> PredicaoCausa:
        del observacao, timeout_seconds
        self.calls += 1
        if self.unavailable:
            raise ConnectionError("servico ML controlado indisponivel")
        return PredicaoCausa("ruptura_de_estoque", 0.92)


class ControlledNotificationChannel:
    def __init__(self, name: str, outcomes: tuple[bool, ...] = (True,)) -> None:
        self.nome = name
        self.outcomes = outcomes
        self.events: list[str] = []

    def enviar(self, alert: Any) -> None:
        self.events.append(str(alert.evento))
        index = min(len(self.events) - 1, len(self.outcomes) - 1)
        if not self.outcomes[index]:
            raise RuntimeError(f"canal {self.nome} indisponivel")


@dataclass(frozen=True)
class LocalPipelineRun:
    scenario: CrisisScenario
    manifest: PipelineManifest
    gateway: InMemoryMaestroGateway
    output_dir: Path
    desktop_result: Mapping[str, object]
    web_result: Mapping[str, object]
    consolidation_result: Mapping[str, object]
    ml_result: Mapping[str, object]
    report_result: CapstoneReportResult
    reference_results: tuple[ReferenceLookupResult, ...]
    reference_attempts: int
    reference_alerts: int
    dependency_states: tuple[str, ...]
    dead_letter_count: int
    channel_events: Mapping[str, tuple[str, ...]]
    elapsed_seconds: float

    @property
    def local_task_states(self) -> dict[str, str]:
        return {
            task.activity_label or CAPSTONE_BOT_LABELS[CapstoneStage.DISPATCHER]: (
                task.finish_status or task.state
            ).upper()
            for task in self.gateway.tasks.values()
        }

    @property
    def artifact_names(self) -> tuple[str, ...]:
        candidates = (
            self.report_result.paths.summary,
            self.report_result.paths.markdown,
            self.report_result.paths.pdf,
            self.report_result.paths.excel,
        )
        return tuple(path.name for path in candidates if path and path.is_file())

    @property
    def dead_letter_path(self) -> Path:
        return self.output_dir / "data" / "dead_letter.jsonl"

    def evidence(self, *, duplicates: int = 0) -> dict[str, object]:
        fallback = (
            self.report_result.snapshot.motivo_fallback
            or self.ml_result.get("motivo_fallback")
        )
        notifications = [
            result.to_dict() for result in self.report_result.notification_results
        ]
        if self.reference_alerts:
            notifications.append(
                {
                    "evento": "base_referencia_indisponivel",
                    "status": "DELIVERED",
                    "quantidade": self.reference_alerts,
                }
            )
        return {
            "schema_version": "1.0",
            "scope": "LOCAL_CONTROLLED",
            "scenario": self.scenario.value,
            "input": {
                "synthetic": True,
                "item_count": 4,
                "item_keys": ["L001", "L002", "L003", "L004"],
            },
            "sabotage": self.scenario.value,
            "observed_states": self.local_task_states,
            "dependency_states": list(self.dependency_states),
            "processed_count": self.report_result.snapshot.processed_items,
            "terminal_count": len(self.gateway.tasks),
            "fallback": fallback,
            "alerts": notifications,
            "reference_alerts": self.reference_alerts,
            "reference_attempts": self.reference_attempts,
            "reference_statuses": [
                result.status.value for result in self.reference_results
            ],
            "dead_letters": self.dead_letter_count,
            "duplicates": duplicates,
            "artifacts": list(self.artifact_names),
            "identifiers": {
                "execution_id": self.manifest.execution_id,
                "correlation_id": self.manifest.correlation_id,
                "root_task_id": self.manifest.root_task_id,
                "task_scope": "local",
                "task_chain": self._task_chain(),
            },
            "elapsed_ms": round(self.elapsed_seconds * 1000),
        }

    def _task_chain(self) -> list[dict[str, object]]:
        chain = []
        for stage, task_id in self.manifest.task_ids.items():
            task = self.gateway.get_task(task_id)
            chain.append(
                {
                    "stage": stage.value,
                    "current_task_id": task.task_id,
                    "parent_task_id": task.parameters.get("parent_task_id"),
                    "predecessor_task_ids": list(task.predecessor_task_ids),
                    "state": (task.finish_status or task.state).upper(),
                }
            )
        return chain

    def reporting_payload(self, **overrides: object) -> dict[str, object]:
        report_task_id = self.manifest.task_ids[CapstoneStage.REPORT]
        payload: dict[str, object] = {
            "report_type": "BUSINESS",
            "execution_id": self.manifest.execution_id,
            "correlation_id": self.manifest.correlation_id,
            "root_task_id": self.manifest.root_task_id,
            "task_id": report_task_id,
            "source_statuses": self.consolidation_result.get(
                "source_statuses",
                {},
            ),
            "consolidation_result": self.consolidation_result,
            "ml_result": self.ml_result,
            "modo_degradado": bool(
                self.consolidation_result.get("modo_degradado")
                or self.ml_result.get("modo_degradado")
            ),
        }
        payload.update(overrides)
        return payload


class LocalCapstonePipeline:
    """Executa componentes reais, substituindo somente integrações externas."""

    def __init__(
        self,
        output_dir: Path,
        scenario: CrisisScenario,
        *,
        real_web: bool = False,
        report_coexistence: CoexistenceCoordinator | None = None,
        report_migration_permit: ExecutionPermit | None = None,
    ) -> None:
        if (report_coexistence is None) != (report_migration_permit is None):
            raise ValueError(
                "report_coexistence e report_migration_permit devem ser informados juntos"
            )
        self.output_dir = output_dir
        self.scenario = scenario
        self.real_web = real_web
        self.report_coexistence = report_coexistence
        self.report_migration_permit = report_migration_permit
        self.execution_id = f"local-exec-{scenario.value}"
        self.correlation_id = f"local-corr-{scenario.value}"
        self.dead_letter_path = output_dir / "data" / "dead_letter.jsonl"
        self.desktop_path = output_dir / "data" / "desktop.json"
        self.web_path = output_dir / "data" / "web.json"
        self.validation_path = output_dir / "data" / "validations.json"
        self.consolidation_path = output_dir / "data" / "consolidation.json"
        self.ml_path = output_dir / "data" / "ml.json"
        self.log_path = output_dir / "logs" / "pipeline.jsonl"
        self.logger = configure_logging(self.log_path)
        self.gateway = InMemoryMaestroGateway(
            f"local-dispatcher-{scenario.value}"
        )
        self.settings = CapstoneOrchestrationSettings(
            desktop_priority=100,
            default_priority=50,
            dependency_timeout_seconds=0.05,
            poll_interval_seconds=0.01,
        )
        self._timed_out_task: str | None = None

    def run(self) -> LocalPipelineRun:
        started = time.monotonic()
        orchestrator = CapstoneOrchestrator(
            self.gateway,
            settings=self.settings,
            wait_function=self._bounded_wait,
        )
        manifest = orchestrator.schedule(
            execution_id=self.execution_id,
            correlation_id=self.correlation_id,
        )
        reference_results, reference_attempts, reference_alerts = (
            self._prepare_validations(manifest)
        )
        desktop_result = self._run_desktop(orchestrator, manifest)

        dependency_states: list[str] = []
        if self.scenario in {
            CrisisScenario.DEPENDENCY_TIMEOUT,
            CrisisScenario.DEPENDENCY_CANCELED,
        }:
            web_result = self._prepare_unavailable_web(manifest)
            web_task_id = manifest.task_ids[CapstoneStage.WEB]
            if self.scenario is CrisisScenario.DEPENDENCY_TIMEOUT:
                self._timed_out_task = web_task_id
            else:
                self.gateway.tasks[web_task_id] = replace(
                    self.gateway.get_task(web_task_id),
                    state="CANCELED",
                    finish_status="CANCELED",
                    finish_message="cancelamento controlado",
                )
        else:
            web_result = self._run_web(orchestrator, manifest)

        consolidation_result, observed_dependencies = self._run_consolidation(
            orchestrator,
            manifest,
        )
        dependency_states.extend(observed_dependencies)
        if self._timed_out_task is not None:
            self.gateway.tasks[self._timed_out_task] = replace(
                self.gateway.get_task(self._timed_out_task),
                state="FINISHED",
                finish_status="TIMEOUT",
                finish_message="timeout local controlado",
            )

        ml_result = self._run_ml(orchestrator, manifest, consolidation_result)
        report_result, channels = self._run_report(
            orchestrator,
            manifest,
            consolidation_result,
            ml_result,
            reference_results,
        )
        return LocalPipelineRun(
            scenario=self.scenario,
            manifest=manifest,
            gateway=self.gateway,
            output_dir=self.output_dir,
            desktop_result=desktop_result,
            web_result=web_result,
            consolidation_result=consolidation_result,
            ml_result=ml_result,
            report_result=report_result,
            reference_results=tuple(reference_results),
            reference_attempts=reference_attempts,
            reference_alerts=reference_alerts,
            dependency_states=tuple(dependency_states),
            dead_letter_count=self._dead_letter_count(),
            channel_events={
                channel.nome: tuple(channel.events) for channel in channels
            },
            elapsed_seconds=time.monotonic() - started,
        )

    def _prepare_validations(
        self,
        manifest: PipelineManifest,
    ) -> tuple[list[ReferenceLookupResult], int, int]:
        items = synthetic_items()
        alerts = ReferenceAlertSpy()
        if self.scenario is CrisisScenario.REFERENCE_UNAVAILABLE:
            gateway: Any = OfflineReferenceGateway()
        else:
            gateway = SelectiveReferenceGateway("L003")
        service = ReferenceBaseService(
            gateway,
            LinearRetryPolicy(3, 0.01, 0.05, sleep=lambda seconds: None),
            DeadLetterWriter(
                self.dead_letter_path,
                execution_id=self.execution_id,
                task_id=manifest.root_task_id,
                now=lambda: datetime(2026, 8, 31, 12, tzinfo=UTC),
            ),
            alert_gateway=alerts,
            logger=self.logger,
        )
        results = []
        validations: list[RegistroValidado] = []
        validator = ValidationService(item["lote_id"] for item in items)
        for index, item in enumerate(items, start=2):
            if self.scenario in {
                CrisisScenario.REFERENCE_UNAVAILABLE,
                CrisisScenario.IRRECOVERABLE_DATA,
            }:
                lookup = service.lookup(item)
                results.append(lookup)
                if lookup.status in {
                    ReferenceLookupStatus.PENDING_REVIEW,
                    ReferenceLookupStatus.DATA_FAILURE,
                }:
                    continue
            validations.append(
                validator.validar_registro(
                    item,
                    aba_origem="Insp_31_08_2026",
                    linha_origem=index,
                )
            )
        self.validation_path.parent.mkdir(parents=True, exist_ok=True)
        self.validation_path.write_text(
            json.dumps(
                [record.to_dict() for record in validations],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        attempts = getattr(gateway, "calls", 0)
        if isinstance(attempts, Mapping):
            attempts = sum(attempts.values())
        return results, int(attempts), len(alerts.messages)

    def _run_desktop(
        self,
        orchestrator: CapstoneOrchestrator,
        manifest: PipelineManifest,
    ) -> Mapping[str, object]:
        task_id = manifest.task_ids[CapstoneStage.DESKTOP]
        self.gateway.activate_task(task_id)
        result: dict[str, Any] = {}

        def handler(context: CapstoneContext) -> StageResult:
            nonlocal result
            result = DesktopStockCollector(
                ControlledDesktopDriver(),
                LinearRetryPolicy(2, 0.01, 0.1, sleep=lambda seconds: None),
                evidence_dir=self.output_dir / "artifacts" / "desktop",
                logger=self.logger,
            ).collect(
                DesktopCollectionContext(
                    execution_id=context.execution_id,
                    correlation_id=context.correlation_id,
                    root_task_id=context.root_task_id,
                    task_id=context.current_task_id,
                    parent_task_id=context.parent_task_id,
                    expected_items=4,
                )
            )
            return _stage_result(result, "coleta desktop concluida")

        orchestrator.execute_current(
            CapstoneStage.DESKTOP,
            handler,
            publisher=lambda context, outcome: _write_json(
                self.desktop_path,
                result,
            ),
        )
        return result

    def _run_web(
        self,
        orchestrator: CapstoneOrchestrator,
        manifest: PipelineManifest,
    ) -> Mapping[str, object]:
        task_id = manifest.task_ids[CapstoneStage.WEB]
        self.gateway.activate_task(task_id)
        result: dict[str, object] = {}

        def handler(context: CapstoneContext) -> StageResult:
            nonlocal result
            config = SupplierPortalConfig(
                url=str(SUPPLIER_PORTAL_PATH),
                username="fornecedor.demo",
                password="demo-local",
                execution_id=context.execution_id,
                correlation_id=context.correlation_id,
                root_task_id=context.root_task_id,
                task_id=context.current_task_id,
                parent_task_id=context.parent_task_id,
                artifact_dir=self.output_dir / "artifacts" / "web",
                timeout_seconds=5,
                max_attempts=1,
                retry_interval_seconds=0.01,
            )
            collector = SupplierPortalCollector(
                config,
                session_factory=(
                    None
                    if self.real_web
                    else lambda attempt: ControlledSupplierSession(
                        config.artifact_dir
                        / f"supplier-success-{context.execution_id}-attempt-{attempt}.png"
                    )
                ),
                sleep=lambda seconds: None,
                logger=self.logger,
            )
            result = collector.collect()
            return _stage_result(result, "coleta web concluida")

        orchestrator.execute_current(
            CapstoneStage.WEB,
            handler,
            publisher=lambda context, outcome: _write_json(self.web_path, result),
        )
        return result

    def _prepare_unavailable_web(
        self,
        manifest: PipelineManifest,
    ) -> Mapping[str, object]:
        task_id = manifest.task_ids[CapstoneStage.WEB]
        result = {
            "schema_version": "1.0",
            "status": "FAILED",
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "root_task_id": manifest.root_task_id,
            "task_id": task_id,
            "parent_task_id": manifest.root_task_id,
            "bot_id": CAPSTONE_BOT_LABELS[CapstoneStage.WEB],
            "modo_degradado": True,
            "motivo_fallback": (
                "timeout"
                if self.scenario is CrisisScenario.DEPENDENCY_TIMEOUT
                else "source_unavailable"
            ),
            "payload": {
                "records": [],
                "source_status": "UNAVAILABLE",
                "collected_items": 0,
                "failed_items": 4,
            },
            "artifacts": [],
        }
        _write_json(self.web_path, result)
        return result

    def _run_consolidation(
        self,
        orchestrator: CapstoneOrchestrator,
        manifest: PipelineManifest,
    ) -> tuple[Mapping[str, object], tuple[str, ...]]:
        task_id = manifest.task_ids[CapstoneStage.CONSOLIDATION]
        self.gateway.activate_task(task_id)
        result: dict[str, object] = {}
        dependencies: tuple[str, ...] = ()

        def handler(context: CapstoneContext) -> StageResult:
            nonlocal result, dependencies
            dependencies = tuple(item.status for item in context.dependency_results)
            result = run_consolidation(
                self.desktop_path,
                self.web_path,
                self.validation_path,
                self.consolidation_path,
            )
            if any(status in {"TIMEOUT", "CANCELED"} for status in dependencies):
                result = {**result, "status": "PARTIALLY_COMPLETED", "modo_degradado": True}
                _write_json(self.consolidation_path, result)
            return _stage_result(result, "consolidacao concluida")

        outcome = orchestrator.execute_current(
            CapstoneStage.CONSOLIDATION,
            handler,
        )
        result = {**result, "status": outcome.result.status}
        _write_json(self.consolidation_path, result)
        return result, dependencies

    def _run_ml(
        self,
        orchestrator: CapstoneOrchestrator,
        manifest: PipelineManifest,
        consolidation: Mapping[str, object],
    ) -> Mapping[str, object]:
        task_id = manifest.task_ids[CapstoneStage.ML]
        self.gateway.activate_task(task_id)
        result: dict[str, Any] = {}

        def handler(context: CapstoneContext) -> StageResult:
            nonlocal result
            provider = ControlledMLProvider(
                unavailable=self.scenario
                in {
                    CrisisScenario.ML_UNAVAILABLE,
                    CrisisScenario.NOTIFICATION_FAILURE,
                    CrisisScenario.CONCURRENCY,
                }
            )
            classifier = ClassificadorDivergencia(
                enabled=True,
                confianca_minima=0.8,
                timeout_seconds=0.1,
                provedor=provider,
            )
            result = MLBotService(
                classifier,
                MLDecisionRecorder(
                    CAPSTONE_BOT_LABELS[CapstoneStage.ML],
                    context.execution_id,
                ),
            ).process(
                consolidation,
                MLBotContext(
                    execution_id=context.execution_id,
                    correlation_id=context.correlation_id,
                    root_task_id=context.root_task_id,
                    task_id=context.current_task_id,
                    parent_task_id=context.parent_task_id,
                    predecessor_task_ids=context.predecessor_task_ids,
                ),
            )
            return _stage_result(result, "classificacao ML concluida")

        orchestrator.execute_current(
            CapstoneStage.ML,
            handler,
            publisher=lambda context, outcome: write_ml_bot_result(
                result,
                self.ml_path,
            ),
        )
        return result

    def _run_report(
        self,
        orchestrator: CapstoneOrchestrator,
        manifest: PipelineManifest,
        consolidation: Mapping[str, object],
        ml_result: Mapping[str, object],
        reference_results: list[ReferenceLookupResult],
    ) -> tuple[CapstoneReportResult, tuple[ControlledNotificationChannel, ...]]:
        task_id = manifest.task_ids[CapstoneStage.REPORT]
        self.gateway.activate_task(task_id)
        report: CapstoneReportResult | None = None
        telegram = ControlledNotificationChannel(
            "telegram",
            (False, False)
            if self.scenario is CrisisScenario.NOTIFICATION_FAILURE
            else (True,),
        )
        email = ControlledNotificationChannel(
            "email",
            (True, False)
            if self.scenario is CrisisScenario.NOTIFICATION_FAILURE
            else (True,),
        )
        local = ControlledNotificationChannel("log_local")
        if self.scenario is CrisisScenario.NOTIFICATION_FAILURE:
            local_channel: Any = CanalLogLocal(self.logger)
        else:
            local_channel = local
        alerts = SistemaAlertas(
            telegram,
            email,
            local_channel,
            logger=self.logger,
        )

        def handler(context: CapstoneContext) -> StageResult:
            nonlocal report
            adjusted_consolidation = dict(consolidation)
            fallback: str | None = None
            degraded_duration = 0
            reference_statuses = {result.status for result in reference_results}
            if ReferenceLookupStatus.PENDING_REVIEW in reference_statuses:
                adjusted_consolidation.update(
                    status="PARTIALLY_COMPLETED",
                    modo_degradado=True,
                )
                fallback = "fonte_indisponivel"
            elif ReferenceLookupStatus.DATA_FAILURE in reference_statuses:
                adjusted_consolidation.update(
                    status="PARTIALLY_COMPLETED",
                    modo_degradado=True,
                )
                fallback = "item_irrecuperavel"
            elif self.scenario is CrisisScenario.NOTIFICATION_FAILURE:
                adjusted_consolidation.update(
                    status="PARTIALLY_COMPLETED",
                    modo_degradado=True,
                )
                fallback = "pipeline_degradado"
                degraded_duration = 301
            payload = {
                "report_type": "BUSINESS",
                "execution_id": context.execution_id,
                "correlation_id": context.correlation_id,
                "root_task_id": context.root_task_id,
                "task_id": context.current_task_id,
                "source_statuses": adjusted_consolidation.get(
                    "source_statuses",
                    {},
                ),
                "consolidation_result": adjusted_consolidation,
                "ml_result": ml_result,
                "modo_degradado": bool(
                    adjusted_consolidation.get("modo_degradado")
                    or ml_result.get("modo_degradado")
                ),
                "motivo_fallback": fallback,
                "degraded_duration_seconds": degraded_duration,
                "dead_letter_produced": self._dead_letter_count() > 0,
            }
            report = CapstoneReportService(
                self.output_dir / "reports",
                alerts=alerts,
                degraded_alert_seconds=300,
                logger=self.logger,
                coexistence=self.report_coexistence,
                migration_permit=self.report_migration_permit,
            ).generate(payload)
            return StageResult(
                report.snapshot.status,
                "relatorio e alertas concluidos",
                payload=report.to_dict(),
                total_items=report.snapshot.total_items,
                processed_items=report.snapshot.processed_items,
                failed_items=report.snapshot.failed_items,
            )

        orchestrator.execute_current(CapstoneStage.REPORT, handler)
        assert report is not None
        return report, (telegram, email, local)

    def _bounded_wait(
        self,
        gateway: InMemoryMaestroGateway,
        task_id: str,
        *,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> Any:
        if task_id == self._timed_out_task:
            moments = iter((0.0, timeout_seconds + 0.001))
            return wait_for_predecessor(
                gateway,
                task_id,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                monotonic=lambda: next(moments),
                sleep=lambda seconds: None,
            )
        return wait_for_predecessor(
            gateway,
            task_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            sleep=lambda seconds: None,
        )

    def _dead_letter_count(self) -> int:
        if not self.dead_letter_path.is_file():
            return 0
        return len(self.dead_letter_path.read_text(encoding="utf-8").splitlines())


class CrisisEvidenceWriter:
    """Persiste resumos determinísticos sem caminhos pessoais ou segredos."""

    REQUIRED_FIELDS = frozenset(
        {
            "schema_version",
            "scope",
            "scenario",
            "input",
            "sabotage",
            "observed_states",
            "processed_count",
            "fallback",
            "alerts",
            "dead_letters",
            "duplicates",
            "artifacts",
            "identifiers",
        }
    )
    SENSITIVE_MARKERS = (
        "password",
        "senha",
        "token",
        "secret",
        "credential",
        "credencial",
        "observacao",
        "recipient",
        "destinatario",
    )
    PERSONAL_PATH = re.compile(r"(?:/home/[^/]+|[A-Za-z]:\\Users\\[^\\]+)")

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def write(self, payload: Mapping[str, object]) -> Path:
        missing = self.REQUIRED_FIELDS - payload.keys()
        if missing:
            raise ValueError(
                "evidencia sem campos obrigatorios: " + ", ".join(sorted(missing))
            )
        sanitized = self._sanitize(payload)
        assert isinstance(sanitized, dict)
        scenario = str(sanitized["scenario"])
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{scenario}.json"
        _write_json(destination, sanitized)
        self._update_index(sanitized)
        return destination

    def _update_index(self, evidence: Mapping[str, object]) -> None:
        index_path = self.directory / "resumo_cenarios.json"
        existing: dict[str, Any] = {
            "schema_version": "1.0",
            "scope": "LOCAL_CONTROLLED",
            "scenarios": [],
        }
        if index_path.is_file():
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        scenarios = {
            str(item["scenario"]): item
            for item in existing.get("scenarios", [])
            if isinstance(item, Mapping) and item.get("scenario")
        }
        scenarios[str(evidence["scenario"])] = dict(evidence)
        existing["scenarios"] = [scenarios[key] for key in sorted(scenarios)]
        _write_json(index_path, existing)

    def _sanitize(self, value: object, key: str = "") -> object:
        folded_key = key.casefold()
        if any(marker in folded_key for marker in self.SENSITIVE_MARKERS):
            return "[REDACTED]"
        if isinstance(value, Mapping):
            return {
                str(child_key): self._sanitize(child, str(child_key))
                for child_key, child in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._sanitize(item, key) for item in value]
        if isinstance(value, Path):
            return value.name
        if isinstance(value, str):
            return self.PERSONAL_PATH.sub("[LOCAL_PATH]", sanitize_text(value))
        return value


def _stage_result(payload: Mapping[str, object], message: str) -> StageResult:
    status = str(payload.get("status") or "FAILED").upper()
    body = payload.get("payload")
    counters = body if isinstance(body, Mapping) else {}
    total = int(
        counters.get("total_items")
        or counters.get("collected_items")
        or 0
    )
    failed = int(counters.get("failed_items") or 0)
    processed = int(counters.get("processed_items") or max(0, total - failed))
    return StageResult(
        status,
        message,
        payload=dict(payload),
        total_items=total,
        processed_items=processed,
        failed_items=failed,
    )


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def assert_sanitized_evidence(path: Path) -> dict[str, object]:
    content = path.read_text(encoding="utf-8")
    lowered = content.casefold()
    forbidden = (
        "demo-local",
        "senha=",
        "token=",
        "segredo-controlado",
        "/home/",
        "c:\\users\\",
    )
    assert not any(value in lowered for value in forbidden)
    payload = json.loads(content)
    assert payload["scope"] == "LOCAL_CONTROLLED"
    identifiers = payload["identifiers"]
    assert identifiers["task_scope"] == "local"
    assert str(identifiers["execution_id"]).startswith("local-")
    assert str(identifiers["correlation_id"]).startswith("local-")
    assert str(identifiers["root_task_id"]).startswith("local-")
    assert len(identifiers["task_chain"]) == 6
    for task in identifiers["task_chain"]:
        assert str(task["current_task_id"]).startswith("local-")
        if task["parent_task_id"] is not None:
            assert str(task["parent_task_id"]).startswith("local-")
        assert all(
            str(predecessor).startswith("local-")
            for predecessor in task["predecessor_task_ids"]
        )
    return payload
