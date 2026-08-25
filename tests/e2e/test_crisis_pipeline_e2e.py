"""Ensaio ponta a ponta com 30 itens e queda do ML durante o lote."""

from __future__ import annotations

import json

import pytest

from src.bot import LotePerformer
from src.classificador_divergencia import (
    ClassificadorDivergencia,
    PredicaoCausa,
)
from src.item_processor import ItemProcessor
from src.logging_config import configure_logging
from src.ml_audit import MLDecisionRecorder
from src.vault_client import VaultClient

pytestmark = pytest.mark.e2e


def synthetic_item(index: int) -> dict[str, object]:
    return {
        "lote_id": f"L{index:03d}",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manha",
        "status": "EM ANALISE",
        "responsavel": "Equipe S10-B",
        "data": "2026-08-25",
        "observacao": f"Caso sintetico {index}",
    }


class TerminalQueue:
    def __init__(self, items) -> None:
        self.items = list(items)
        self.done = []
        self.reviews = []
        self.business_errors = []
        self.system_errors = []

    def has_next(self):
        return bool(self.items)

    def next(self):
        return self.items.pop(0)

    def mark_done(self, item, result):
        self.done.append((item, result))

    def mark_human_review(self, item, review, result):
        self.reviews.append((item, review, result))

    def mark_business_error(self, item, error, result):
        self.business_errors.append((item, error, result))

    def mark_system_error(self, item, error, result):
        self.system_errors.append((item, error, result))

    @property
    def terminal_count(self):
        return sum(
            len(group)
            for group in (
                self.done,
                self.reviews,
                self.business_errors,
                self.system_errors,
            )
        )


class FakeVaultProvider:
    def get_credential(self, label):
        del label
        return {"username": "ensaio.erp", "password": "senha-efemera"}


class MLDropDuringBatch:
    def __init__(self, available_calls: int) -> None:
        self.available_calls = available_calls
        self.calls = 0

    def classificar(self, observacao: str, timeout_seconds: float):
        del observacao, timeout_seconds
        self.calls += 1
        if self.calls > self.available_calls:
            raise ConnectionError("ML derrubado; token=segredo-que-nao-pode-vazar")
        return PredicaoCausa("falha_calibracao", 0.95)


def test_ensaio_de_crise_finaliza_os_30_casos_apos_queda_do_ml(tmp_path):
    log_file = tmp_path / "ensaio-crise-30-casos.log"
    configure_logging(log_file)
    items = [synthetic_item(index) for index in range(1, 31)]
    queue = TerminalQueue(items)
    provider = MLDropDuringBatch(available_calls=10)
    classifier = ClassificadorDivergencia(
        enabled=True,
        confianca_minima=0.8,
        timeout_seconds=0.2,
        provedor=provider,
    )
    processor = ItemProcessor(
        {item["lote_id"] for item in items},
        divergence_classifier=classifier,
        decision_recorder=MLDecisionRecorder("bot-crise", "exec-30-casos"),
    )

    result = LotePerformer(
        queue,
        {item["lote_id"] for item in items},
        VaultClient(FakeVaultProvider()),
        item_processor=processor,
    ).run()

    origins = [decision.origem_decisao for decision in result.ml_decisions]
    reasons = [decision.motivo_fallback for decision in result.ml_decisions]
    log_content = log_file.read_text(encoding="utf-8")
    evidence = {
        "cenario": "massa_sintetica_30_casos",
        "total": result.total,
        "terminais": queue.terminal_count,
        "ml": origins.count("ml"),
        "fallback": origins.count("fallback"),
        "motivo_fallback": "indisponibilidade",
        "erros_sistema": result.system_errors,
    }

    assert result.total == 30
    assert queue.terminal_count == 30
    assert len(queue.reviews) == 30
    assert result.system_errors == 0
    assert origins == ["ml"] * 10 + ["fallback"] * 20
    assert reasons[10:] == ["indisponibilidade"] * 20
    assert "segredo-que-nao-pode-vazar" not in log_content
    print("CRISIS_EVIDENCE " + json.dumps(evidence, sort_keys=True))
