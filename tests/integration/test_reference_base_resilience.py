from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.bot import LotePerformer
from src.dead_letter import DeadLetterWriter
from src.item_processor import ItemProcessor
from src.reference_base import (
    ReferenceBaseService,
    ReferenceInfrastructureError,
    ReferenceLookupStatus,
)
from src.retry_policy import LinearRetryPolicy
from src.vault_client import ErpCredential

pytestmark = pytest.mark.integration


def valid_item(lote_id: str = "L001") -> dict[str, object]:
    return {
        "lote_id": lote_id,
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manhã",
        "status": "APROVADO",
        "responsavel": "Marcelo",
        "data": "25/08/2026",
        "observacao": "",
    }


class SequenceReferenceGateway:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.timeouts = []

    def contains(self, lote_id, *, timeout_seconds):
        self.timeouts.append(timeout_seconds)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class AlertRecorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.messages = []
        self.fail = fail

    def send_error_alert(self, message):
        self.messages.append(message)
        if self.fail:
            raise RuntimeError("canal de alerta indisponível")


def build_service(
    tmp_path,
    gateway,
    *,
    max_attempts=3,
    sleep=lambda seconds: None,
    alert_gateway=None,
):
    return ReferenceBaseService(
        gateway,
        LinearRetryPolicy(
            max_attempts,
            1,
            4,
            sleep=sleep,
        ),
        DeadLetterWriter(
            tmp_path / "data" / "output" / "dead_letter.jsonl",
            execution_id="exec-96",
            task_id="task-96",
        ),
        alert_gateway=alert_gateway,
    )


def test_base_transitoria_recupera_com_backoff_linear_sem_dead_letter(tmp_path):
    gateway = SequenceReferenceGateway([
        ReferenceInfrastructureError("indisponível 1"),
        ReferenceInfrastructureError("indisponível 2"),
        True,
    ])
    sleeps = []
    service = build_service(
        tmp_path,
        gateway,
        sleep=lambda seconds: sleeps.append(seconds),
    )

    result = service.lookup(valid_item())

    assert result.status is ReferenceLookupStatus.FOUND
    assert result.attempts == 3
    assert sleeps == [1, 2]
    assert gateway.timeouts == [4, 4, 4]
    assert not (tmp_path / "data/output/dead_letter.jsonl").exists()


def test_falhas_mistas_respeitam_limite_global_e_nao_geram_dead_letter(tmp_path):
    gateway = SequenceReferenceGateway([
        ReferenceInfrastructureError("indisponível 1"),
        {"resposta": "inválida"},
        ReferenceInfrastructureError("indisponível 2"),
    ])
    sleeps = []
    alert = AlertRecorder()
    service = build_service(
        tmp_path,
        gateway,
        sleep=lambda seconds: sleeps.append(seconds),
        alert_gateway=alert,
    )

    result = service.lookup(valid_item())

    assert result.status is ReferenceLookupStatus.PENDING_REVIEW
    assert result.attempts == 3
    assert gateway.timeouts == [4, 4, 4]
    assert sleeps == [1]
    assert len(alert.messages) == 1
    assert not (tmp_path / "data/output/dead_letter.jsonl").exists()


class OfflineReferenceGateway:
    def __init__(self) -> None:
        self.calls = 0

    def contains(self, lote_id, *, timeout_seconds):
        self.calls += 1
        raise ReferenceInfrastructureError(
            f"Base offline para {lote_id}; timeout={timeout_seconds}"
        )


class InMemoryQueue:
    def __init__(self, items) -> None:
        self.items = list(items)
        self.reviews = []
        self.business_errors = []
        self.system_errors = []

    def has_next(self):
        return bool(self.items)

    def next(self):
        return self.items.pop(0) if self.items else None

    def mark_done(self, item, result):
        raise AssertionError("item pendente não pode ser finalizado como sucesso")

    def mark_business_error(self, item, error, result):
        self.business_errors.append((item, error, result))

    def mark_system_error(self, item, error, result):
        self.system_errors.append((item, error, result))

    def mark_human_review(self, item, review, result):
        self.reviews.append((item, review, result))


class FakeVault:
    def get_erp_credential(self):
        return ErpCredential("usuario-teste", "senha-efemera")


def test_base_persistentemente_offline_mantem_consumo_e_solicita_alerta(tmp_path):
    gateway = OfflineReferenceGateway()
    alert = AlertRecorder()
    service = build_service(tmp_path, gateway, alert_gateway=alert)
    processor = ItemProcessor(("L001", "L002"), reference_base=service)
    queue = InMemoryQueue([valid_item("L001"), valid_item("L002")])
    performer = LotePerformer(
        queue,
        ("L001", "L002"),
        FakeVault(),
        item_processor=processor,
    )

    result = performer.run()

    assert result.total == 2
    assert result.system_errors == 0
    assert len(result.human_reviews) == 2
    assert len(queue.reviews) == 2
    assert all(
        output["resultado_validacao"] == "PENDENTE_REVISAO"
        for _, _, output in queue.reviews
    )
    assert [item["lote_id"] for item, _, _ in queue.reviews] == ["L001", "L002"]
    assert all(
        review.reason == output["mensagem_resultado"]
        and "Base de Referência indisponível" in review.reason
        for _, review, output in queue.reviews
    )
    assert gateway.calls == 6
    assert len(alert.messages) == 2
    assert all("PENDENTE_REVISAO" in message for message in alert.messages)
    assert not (tmp_path / "data/output/dead_letter.jsonl").exists()


def test_falha_do_canal_de_alerta_nao_interrompe_fallback(tmp_path):
    gateway = OfflineReferenceGateway()
    alert = AlertRecorder(fail=True)
    service = build_service(tmp_path, gateway, alert_gateway=alert)

    result = service.lookup(valid_item())

    assert result.status is ReferenceLookupStatus.PENDING_REVIEW
    assert len(alert.messages) == 1


def test_lote_ausente_preserva_rn03_sem_retry_ou_dead_letter(tmp_path):
    gateway = SequenceReferenceGateway([False])
    service = build_service(tmp_path, gateway)
    processor = ItemProcessor(("L001",), reference_base=service)

    classification = processor.process(valid_item("L999"))

    assert classification.resultado == "DIVERGENCIA"
    assert classification.mensagem.startswith("RN03")
    assert gateway.timeouts == [4]
    assert not (tmp_path / "data/output/dead_letter.jsonl").exists()


@pytest.mark.parametrize(
    ("item", "expected_rule"),
    [
        (
            {
                key: value
                for key, value in valid_item().items()
                if key != "observacao"
            },
            "RN01",
        ),
        ({**valid_item(), "produto": ""}, "RN02"),
    ],
)
def test_campos_rn01_rn02_sao_validados_antes_da_base(
    tmp_path,
    item,
    expected_rule,
):
    gateway = SequenceReferenceGateway([True])
    service = build_service(tmp_path, gateway)
    processor = ItemProcessor(("L001",), reference_base=service)
    current_item: Mapping[str, object] = item

    classification = processor.process(current_item)

    assert classification.resultado == "DIVERGENCIA"
    assert classification.mensagem.startswith(expected_rule)
    assert gateway.timeouts == []
