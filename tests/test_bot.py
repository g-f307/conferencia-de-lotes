import logging

from src.bot import LotePerformer
from src.vault_client import VaultClient


class FakeQueue:
    def __init__(self, items):
        self.items = list(items)
        self.done = []
        self.business_errors = []
        self.system_errors = []
        self.human_reviews = []

    def has_next(self):
        return bool(self.items)

    def next(self):
        return self.items.pop(0)

    def mark_done(self, item, result):
        self.done.append((item, result))

    def mark_business_error(self, item, error):
        self.business_errors.append((item, error))

    def mark_system_error(self, item, error):
        self.system_errors.append((item, error))

    def mark_human_review(self, item, review):
        self.human_reviews.append((item, review))


class FakeVaultProvider:
    def get_credential(self, label):
        assert label == "credencial_erp"
        return {"username": "rebecca.erp", "password": "fake-password-for-test"}


def item(**overrides):
    data = {
        "lote_id": "L001",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manha",
        "status": "APROVADO",
        "responsavel": "Rebecca",
        "data": "2026-07-19",
        "observacao": "",
    }
    data.update(overrides)
    return data


def test_performer_continues_after_validation_error():
    queue = FakeQueue([item(produto=""), item(lote_id="L002")])
    performer = LotePerformer(queue, {"L001", "L002"}, VaultClient(FakeVaultProvider()))

    result = performer.run()

    assert result.total == 2
    assert result.business_errors == 1
    assert result.success == 1
    assert len(queue.business_errors) == 1
    assert len(queue.done) == 1


def test_performer_separates_ambiguous_status_for_human_review():
    queue = FakeQueue([item(status="em analise")])
    performer = LotePerformer(queue, {"L001"}, VaultClient(FakeVaultProvider()))

    result = performer.run()

    assert result.business_errors == 0
    assert result.success == 0
    assert len(result.human_reviews) == 1
    assert queue.human_reviews[0][1].lote_id == "L001"


def test_performer_logs_only_username_not_password(caplog):
    queue = FakeQueue([item()])
    performer = LotePerformer(queue, {"L001"}, VaultClient(FakeVaultProvider()))

    with caplog.at_level(logging.INFO):
        performer.run()

    log_text = caplog.text
    assert "rebecca.erp" in log_text
    assert "fake-password-for-test" not in log_text


def test_performer_stops_when_datapool_returns_empty_item():
    class EmptyQueue(FakeQueue):
        def __init__(self):
            super().__init__([])
            self.called = False

        def has_next(self):
            return not self.called

        def next(self):
            self.called = True
            return None

    queue = EmptyQueue()
    performer = LotePerformer(queue, {"L001"}, VaultClient(FakeVaultProvider()))

    result = performer.run()

    assert result.total == 0
    assert queue.done == []
    assert queue.business_errors == []
    assert queue.system_errors == []
