from __future__ import annotations

import json
import threading
from datetime import UTC, datetime

import pytest

from src.dead_letter import DeadLetterWriter
from src.reference_base import (
    ReferenceBaseService,
    ReferenceLookupStatus,
)
from src.retry_policy import LinearRetryPolicy

pytestmark = pytest.mark.integration


def lote_com_dados_sensiveis() -> dict[str, object]:
    return {
        "lote_id": "L001",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manhã",
        "status": "APROVADO",
        "responsavel": "Marcelo",
        "data": "25/08/2026",
        "observacao": "observação sigilosa do operador",
        "token": "token-super-secreto",
        "password": "senha-super-secreta",
    }


def test_dead_letter_grava_contrato_sanitizado_e_rastreavel(tmp_path):
    path = tmp_path / "data" / "output" / "dead_letter.jsonl"
    writer = DeadLetterWriter(
        path,
        execution_id="exec-96",
        task_id="task-96",
        now=lambda: datetime(2026, 8, 25, 12, 30, tzinfo=UTC),
    )

    written = writer.write(
        lote_com_dados_sensiveis(),
        reason="payload inválido; password=segredo",
        attempts=3,
    )

    record = json.loads(path.read_text(encoding="utf-8"))
    raw_content = path.read_text(encoding="utf-8")
    assert written is True
    assert record["item"]["lote_id"] == "L001"
    assert "observacao" not in record["item"]
    assert "token" not in record["item"]
    assert "password" not in record["item"]
    assert record["motivo"] == "payload inválido; password=[REDACTED]"
    assert record["tentativas"] == 3
    assert record["timestamp"] == "2026-08-25T12:30:00+00:00"
    assert record["execution_id"] == "exec-96"
    assert record["task_id"] == "task-96"
    assert len(record["deduplication_key"]) == 64
    assert "sigilosa" not in raw_content
    assert "token-super-secreto" not in raw_content
    assert "senha-super-secreta" not in raw_content
    assert "password=segredo" not in raw_content


def test_dead_letter_evitar_duplicacao_inclusive_entre_instancias(tmp_path):
    path = tmp_path / "data" / "output" / "dead_letter.jsonl"
    item = lote_com_dados_sensiveis()
    first = DeadLetterWriter(path, execution_id="exec-96", task_id="task-96")
    second = DeadLetterWriter(path, execution_id="exec-96", task_id="task-96")

    assert first.write(item, reason="dado inválido", attempts=3) is True
    assert second.write(item, reason="dado inválido", attempts=3) is False

    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_dead_letter_evitar_duplicacao_em_gravacoes_concorrentes(tmp_path):
    path = tmp_path / "data" / "output" / "dead_letter.jsonl"
    item = lote_com_dados_sensiveis()
    writers = [
        DeadLetterWriter(path, execution_id="exec-96", task_id="task-96")
        for _ in range(2)
    ]
    barrier = threading.Barrier(2)
    results = []

    def write(writer):
        barrier.wait()
        results.append(
            writer.write(item, reason="dado inválido", attempts=3)
        )

    threads = [threading.Thread(target=write, args=(writer,)) for writer in writers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [False, True]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


class InvalidDataGateway:
    def __init__(self) -> None:
        self.calls = 0

    def contains(self, lote_id, *, timeout_seconds):
        self.calls += 1
        return {"lote_id": lote_id, "timeout": timeout_seconds}


def test_falha_repetida_de_dados_cria_dead_letter_sem_sleep(tmp_path):
    path = tmp_path / "data" / "output" / "dead_letter.jsonl"
    gateway = InvalidDataGateway()
    sleeps = []
    writer = DeadLetterWriter(path, execution_id="exec-96", task_id="task-96")
    service = ReferenceBaseService(
        gateway,
        LinearRetryPolicy(
            3,
            1,
            5,
            sleep=lambda seconds: sleeps.append(seconds),
        ),
        writer,
    )

    result = service.lookup(lote_com_dados_sensiveis())

    assert result.status is ReferenceLookupStatus.DATA_FAILURE
    assert result.attempts == 3
    assert gateway.calls == 3
    assert sleeps == []
    assert path.is_file()
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_dead_letter_rejeita_rastreabilidade_ou_tentativas_invalidas(tmp_path):
    with pytest.raises(ValueError, match="execution_id"):
        DeadLetterWriter(tmp_path / "dead.jsonl", execution_id="", task_id="task")

    writer = DeadLetterWriter(
        tmp_path / "dead.jsonl",
        execution_id="exec",
        task_id="task",
    )
    with pytest.raises(ValueError, match="attempts"):
        writer.write({}, reason="falha", attempts=0)
