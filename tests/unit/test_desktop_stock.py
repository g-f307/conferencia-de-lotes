"""Testes unitários dos contratos e da coleta visual de estoque."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.desktop_stock.collector import DesktopStockCollector, parse_visible_stock
from src.desktop_stock.driver import DesktopAutomationError
from src.desktop_stock.models import DesktopCollectionContext
from src.retry_policy import LinearRetryPolicy

VISIBLE_STOCK = """lote_id\tproduto\tquantidade_disponivel\tlocalizacao\tstatus_estoque\tatualizado_em
L001\tMonitor\t18\tA-01\tDISPONIVEL\t2026-08-26T12:00:00+00:00
L002\tTeclado\t4\tA-02\tBAIXO\t2026-08-26T12:02:00+00:00"""


class FakeDesktopDriver:
    def __init__(self, *, failures: int = 0, visible_text: str = VISIBLE_STOCK):
        self.failures = failures
        self.visible_text = visible_text
        self.searches: list[str] = []
        self.wait_calls = 0
        self.closed = False

    def wait_until_ready(self, timeout_seconds: float) -> None:
        self.wait_calls += 1
        if self.wait_calls <= self.failures:
            raise DesktopAutomationError("janela indisponível")

    def search(self, query: str, timeout_seconds: float) -> None:
        self.searches.append(query)

    def read_visible_records(self, timeout_seconds: float) -> str:
        return self.visible_text

    def capture_evidence(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-png")
        return destination

    def close(self) -> None:
        self.closed = True


def make_context(expected_items: int | None = 2) -> DesktopCollectionContext:
    return DesktopCollectionContext(
        execution_id="exec-001",
        correlation_id="corr-001",
        root_task_id="root-001",
        task_id="desktop-001",
        parent_task_id="dispatcher-001",
        expected_items=expected_items,
    )


def make_policy(max_attempts: int = 2) -> LinearRetryPolicy:
    ticks = iter((0.0, 0.1, 0.2, 0.3, 0.4))
    return LinearRetryPolicy(
        max_attempts=max_attempts,
        base_interval_seconds=0.01,
        timeout_seconds=1.0,
        sleep=lambda _seconds: None,
        clock=lambda: next(ticks),
    )


@pytest.mark.unit
def test_parse_visible_stock_converts_the_six_contract_fields() -> None:
    records = parse_visible_stock(VISIBLE_STOCK)

    assert [record.lote_id for record in records] == ["L001", "L002"]
    assert records[0].quantidade_disponivel == 18
    assert records[1].status_estoque == "BAIXO"


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid_text",
    [
        "lote_id\tproduto\nL001\tMonitor",
        VISIBLE_STOCK.replace("\t18\t", "\t-1\t"),
        VISIBLE_STOCK.replace("\tMonitor\t", "\t\t"),
    ],
    ids=("cabecalho", "quantidade-negativa", "campo-vazio"),
)
def test_parse_visible_stock_rejects_invalid_visual_content(
    invalid_text: str,
) -> None:
    with pytest.raises(DesktopAutomationError):
        parse_visible_stock(invalid_text)


@pytest.mark.unit
def test_collection_returns_architecture_envelope_and_evidence(
    tmp_path: Path,
) -> None:
    driver = FakeDesktopDriver()
    collector = DesktopStockCollector(
        driver,
        make_policy(),
        evidence_dir=tmp_path,
        clock=lambda: 10.0,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
    )

    result = collector.collect(make_context())

    assert result["status"] == "SUCCESS"
    assert result["bot_id"] == "estoque-desktop-v1"
    assert result["origem_dados"] == ["desktop"]
    assert result["payload"]["source_status"] == "AVAILABLE"
    assert result["payload"]["collected_items"] == 2
    assert result["payload"]["records"][0]["produto"] == "Monitor"
    assert result["artifacts"][0]["checksum_sha256"]
    assert driver.searches == ["*"]
    assert driver.closed is True


@pytest.mark.unit
def test_collection_retries_and_returns_safe_fallback(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    driver = FakeDesktopDriver(failures=3)
    logger = logging.getLogger("desktop-test")
    collector = DesktopStockCollector(
        driver,
        make_policy(max_attempts=2),
        evidence_dir=tmp_path,
        logger=logger,
        clock=lambda: 10.0,
    )

    with caplog.at_level(logging.INFO, logger="desktop-test"):
        result = collector.collect(make_context(expected_items=5))

    assert result["status"] == "PARTIALLY_COMPLETED"
    assert result["payload"]["source_status"] == "UNAVAILABLE"
    assert result["payload"]["failed_items"] == 5
    assert result["motivo_fallback"] == "desktop_unavailable_after_retry"
    assert result["attempts"] == 2
    assert result["payload"]["records"] == []
    assert len(result["payload"]["evidence_paths"]) == 3
    assert driver.wait_calls == 2
    assert driver.closed is True
    assert "DESKTOP_COLLECTION_FALLBACK" in caplog.messages
    fallback_record = next(
        record
        for record in caplog.records
        if record.message == "DESKTOP_COLLECTION_FALLBACK"
    )
    assert fallback_record.attempts == 2
    assert fallback_record.latency_ms == 0
    assert fallback_record.failed_items == 5
    assert fallback_record.source_status == "UNAVAILABLE"


@pytest.mark.unit
def test_collection_context_rejects_empty_identifiers() -> None:
    with pytest.raises(ValueError, match="não podem ser vazios"):
        DesktopCollectionContext(
            execution_id="",
            correlation_id="corr",
            root_task_id="root",
            task_id="task",
            parent_task_id="parent",
        )
