from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.supplier_portal import (
    BOT_ID,
    SupplierOrder,
    SupplierPortalAuthenticationError,
    SupplierPortalCollector,
    SupplierPortalConfig,
    SupplierPortalDataError,
    SupplierPortalTimeoutError,
    SupplierPortalUnavailableError,
    SupplierSessionResult,
    build_supplier_evidence_path,
    resolve_supplier_login_url,
    resolve_supplier_url,
)

pytestmark = pytest.mark.unit


class FakeClock:
    def __init__(self) -> None:
        self.value = 10.0

    def __call__(self) -> float:
        self.value += 0.025
        return self.value


class FakeSession:
    def __init__(self, outcome):
        self.outcome = outcome

    def collect(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeLogger:
    def __init__(self) -> None:
        self.events = []

    def info(self, message, *, extra) -> None:
        self.events.append((message, extra))


def config(tmp_path: Path, **overrides) -> SupplierPortalConfig:
    values = {
        "url": "web/supplier-portal/index.html",
        "username": "fornecedor.demo",
        "password": "demo-local",
        "execution_id": "exec-unit-001",
        "correlation_id": "corr-unit-001",
        "root_task_id": "root-unit-001",
        "task_id": "task-web-001",
        "parent_task_id": "task-dispatcher-001",
        "artifact_dir": tmp_path / "evidencias",
        "timeout_seconds": 2.0,
        "max_attempts": 3,
        "retry_interval_seconds": 0.1,
    }
    values.update(overrides)
    return SupplierPortalConfig(**values)


def order() -> SupplierOrder:
    return SupplierOrder.from_mapping(
        {
            "pedido_id": "PED-1",
            "lote_id": "L001",
            "fornecedor": "Fornecedor",
            "produto": "Monitor",
            "quantidade_solicitada": "20",
            "status_pedido": "CONFIRMADO",
            "data_prevista": "28/08/2026",
        }
    )


def success_result(tmp_path: Path) -> SupplierSessionResult:
    evidence = tmp_path / "evidencia.png"
    evidence.write_bytes(b"\x89PNG\r\n\x1a\ncontrolled")
    return SupplierSessionResult((order(),), evidence)


def test_coleta_nominal_produz_envelope_completo(tmp_path: Path) -> None:
    current_config = config(tmp_path)
    result = SupplierPortalCollector(
        current_config,
        session_factory=lambda _attempt: FakeSession(success_result(tmp_path)),
        sleep=lambda _seconds: None,
        clock=FakeClock(),
        now=lambda: datetime(2026, 8, 26, 14, tzinfo=timezone.utc),
    ).collect()

    assert result["status"] == "SUCCESS"
    assert result["bot_id"] == BOT_ID
    assert result["attempts"] == 1
    assert result["origem_dados"] == ["web"]
    assert result["predecessor_task_ids"] == ["task-dispatcher-001"]
    assert result["payload"]["records"] == [order().to_dict()]
    assert result["payload"]["source_status"] == "AVAILABLE"
    assert result["payload"]["collected_items"] == 1
    assert result["payload"]["started_at"] == "2026-08-26T14:00:00+00:00"
    assert result["payload"]["completed_at"] == "2026-08-26T14:00:00+00:00"
    assert len(result["artifacts"][0]["checksum"]) == 64


def test_timeout_e_retentado_antes_do_sucesso(tmp_path: Path) -> None:
    outcomes = [
        SupplierPortalTimeoutError("portal lento"),
        success_result(tmp_path),
    ]
    sleeps = []
    result = SupplierPortalCollector(
        config(tmp_path),
        session_factory=lambda attempt: FakeSession(outcomes[attempt - 1]),
        sleep=sleeps.append,
        clock=FakeClock(),
    ).collect()

    assert result["status"] == "SUCCESS"
    assert result["attempts"] == 2
    assert sleeps == [0.1]


def test_eventos_estruturados_registram_ciclo_sem_credenciais(tmp_path: Path) -> None:
    logger = FakeLogger()
    result = SupplierPortalCollector(
        config(tmp_path),
        session_factory=lambda _attempt: FakeSession(success_result(tmp_path)),
        sleep=lambda _seconds: None,
        clock=FakeClock(),
        logger=logger,
    ).collect()

    assert result["status"] == "SUCCESS"
    assert [message for message, _extra in logger.events] == [
        "supplier_collection_started",
        "supplier_collection_attempt_started",
        "supplier_collection_succeeded",
    ]
    final_event = logger.events[-1][1]
    assert final_event["execution_id"] == "exec-unit-001"
    assert final_event["attempts"] == 1
    assert final_event["collected_items"] == 1
    assert final_event["failed_items"] == 0
    assert final_event["latency_ms"] >= 0
    assert "username" not in final_event
    assert "password" not in final_event


@pytest.mark.parametrize(
    ("error", "failure_type", "fallback", "expected_attempts"),
    [
        (
            SupplierPortalUnavailableError("portal fora do ar"),
            "UNAVAILABLE",
            "source_unavailable",
            3,
        ),
        (
            SupplierPortalTimeoutError("portal lento"),
            "TIMEOUT",
            "timeout",
            3,
        ),
        (
            SupplierPortalAuthenticationError("acesso recusado"),
            "AUTHENTICATION",
            "authentication_failed",
            1,
        ),
        (
            SupplierPortalDataError("pedido inválido"),
            "INVALID_DATA",
            "invalid_source_data",
            1,
        ),
    ],
)
def test_falhas_controladas_terminam_sem_espera_infinita(
    tmp_path: Path,
    error: Exception,
    failure_type: str,
    fallback: str,
    expected_attempts: int,
) -> None:
    attempts = []

    def factory(attempt):
        attempts.append(attempt)
        return FakeSession(error)

    result = SupplierPortalCollector(
        config(tmp_path),
        session_factory=factory,
        sleep=lambda _seconds: None,
        clock=FakeClock(),
    ).collect()

    assert result["status"] == "FAILED"
    assert result["payload"]["source_status"] == "UNAVAILABLE"
    assert result["payload"]["failure_type"] == failure_type
    assert result["motivo_fallback"] == fallback
    assert result["attempts"] == expected_attempts
    assert attempts == list(range(1, expected_attempts + 1))


def test_pedido_invalido_nao_e_normalizado_silenciosamente() -> None:
    with pytest.raises(SupplierPortalDataError, match="quantidade"):
        SupplierOrder.from_mapping(
            {
                "pedido_id": "PED-1",
                "lote_id": "L001",
                "fornecedor": "Fornecedor",
                "produto": "Monitor",
                "quantidade_solicitada": "zero",
                "status_pedido": "CONFIRMADO",
                "data_prevista": "28/08/2026",
            }
        )


def test_configuracao_nao_expoe_senha_no_repr(tmp_path: Path) -> None:
    assert "demo-local" not in repr(config(tmp_path))


def test_nome_da_evidencia_contem_execucao_tentativa_e_utc(tmp_path: Path) -> None:
    result = build_supplier_evidence_path(
        tmp_path,
        "exec/001",
        2,
        now=datetime(2026, 8, 26, 14, tzinfo=timezone.utc),
    )

    assert result.name == "supplier-success-exec-001-attempt-2-20260826T140000000000Z.png"


def test_caminho_absoluto_windows_e_convertido_em_url_file(tmp_path: Path) -> None:
    portal = tmp_path / "portal" / "index.html"
    portal.parent.mkdir()
    portal.write_text("<html></html>", encoding="utf-8")

    application_url = resolve_supplier_url(str(portal))

    assert application_url.startswith("file:///")
    assert resolve_supplier_login_url(application_url).endswith("/login.html")
