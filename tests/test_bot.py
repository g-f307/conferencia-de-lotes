import logging

import pytest

from src.bot import LotePerformer, QueueItemFetchError
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

    def mark_business_error(self, item, error, result):
        self.business_errors.append((item, error, result))

    def mark_system_error(self, item, error, result):
        self.system_errors.append((item, error, result))

    def mark_human_review(self, item, review, result):
        self.human_reviews.append((item, review, result))


class OrderedQueue(FakeQueue):
    def __init__(self, items, events):
        super().__init__(items)
        self.events = events

    def mark_done(self, item, result):
        self.events.append("mark_done")
        super().mark_done(item, result)


class FakeVaultProvider:
    def get_credential(self, label):
        assert label == "credencial_erp2"
        return {"username": "rebecca.erp", "password": "fake-password-for-test"}


class FakeWebProcessor:
    def __init__(self, base_dir, *, fail_lotes=()):
        self.base_dir = base_dir
        self.fail_lotes = set(fail_lotes)
        self.calls = []
        self.error_captures = []

    def process_item(self, item, resultado_validacao, mensagem_resultado):
        self.calls.append(
            (item["lote_id"], resultado_validacao, mensagem_resultado)
        )
        if item["lote_id"] in self.fail_lotes:
            raise RuntimeError("formulario indisponivel")
        prefix = {
            "APROVADO": "aprovado",
            "REPROVADO": "reprovado",
            "DIVERGENCIA": "divergencia",
            "REVISAO": "divergencia",
        }[resultado_validacao]
        evidence = self.base_dir / "artefatos" / f"{prefix}-{item['lote_id']}.png"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_bytes(b"fake-png")
        return type(
            "WebResult",
            (),
            {
                "evidence_path": evidence,
                "mensagem_resultado": (
                    f"Resultado confirmado na interface: {resultado_validacao}"
                ),
            },
        )()

    def capture_error(self, item):
        self.error_captures.append(item["lote_id"])
        evidence = self.base_dir / "artefatos" / f"erro-{item['lote_id']}.png"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_bytes(b"fake-png")
        return evidence


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
    assert queue.human_reviews[0][2]["resultado_validacao"] == "REVISAO"


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


def test_performer_propagates_when_next_raises_without_marking_item():
    class BrokenQueue(FakeQueue):
        def __init__(self):
            super().__init__([])

        def has_next(self):
            return True

        def next(self):
            raise RuntimeError("fila indisponivel")

    queue = BrokenQueue()
    performer = LotePerformer(queue, {"L001"}, VaultClient(FakeVaultProvider()))

    with pytest.raises(QueueItemFetchError):
        performer.run()

    assert queue.system_errors == []


def test_performer_aplica_atraso_configurado_sem_alterar_resultado():
    events = []
    queue = OrderedQueue([item()], events)
    performer = LotePerformer(
        queue,
        {"L001"},
        VaultClient(FakeVaultProvider()),
        processing_delay_seconds=1,
        sleep_fn=lambda seconds: events.append(f"sleep:{seconds}"),
    )

    performer.run()

    assert events == ["mark_done", "sleep:1"]


def test_performer_does_not_wait_on_business_error_or_human_review():
    sleeps = []
    queue = FakeQueue([item(produto=""), item(status="pendente")])
    performer = LotePerformer(
        queue,
        {"L001"},
        VaultClient(FakeVaultProvider()),
        processing_delay_seconds=1,
        sleep_fn=sleeps.append,
    )

    performer.run()

    assert sleeps == []
    assert len(queue.business_errors) == 1
    assert len(queue.human_reviews) == 1


def test_performer_processa_cada_item_na_web_e_grava_saidas(tmp_path):
    queue = FakeQueue(
        [
            item(lote_id="L001", status="APROVADO"),
            item(lote_id="L002", status="REPROVADO", observacao="Avaria"),
            item(lote_id="L003", status="em analise"),
        ]
    )
    web = FakeWebProcessor(tmp_path)
    performer = LotePerformer(
        queue,
        {"L001", "L002", "L003"},
        VaultClient(FakeVaultProvider()),
        web_processor=web,
    )

    result = performer.run()

    assert result.total == 3
    assert result.success == 2
    assert result.approved == 1
    assert result.rejected == 1
    assert result.divergences == 0
    assert len(result.human_reviews) == 1
    assert [call[:2] for call in web.calls] == [
        ("L001", "APROVADO"),
        ("L002", "REPROVADO"),
        ("L003", "REVISAO"),
    ]
    assert queue.done[0][1]["resultado_validacao"] == "APROVADO"
    assert queue.done[0][1]["evidencia"] == "artefatos/aprovado-L001.png"
    assert (
        queue.done[0][1]["mensagem_resultado"]
        == "Resultado confirmado na interface: APROVADO"
    )
    assert queue.done[1][1]["resultado_validacao"] == "REPROVADO"
    assert (
        queue.done[1][1]["mensagem_resultado"]
        == "Resultado confirmado na interface: REPROVADO"
    )
    assert queue.business_errors == []
    assert queue.human_reviews[0][2]["resultado_validacao"] == "REVISAO"
    assert result.evidences == [
        "artefatos/aprovado-L001.png",
        "artefatos/reprovado-L002.png",
        "artefatos/divergencia-L003.png",
    ]


def test_performer_isola_falha_web_e_continua_proximo_item(tmp_path):
    queue = FakeQueue([item(lote_id="L001"), item(lote_id="L002")])
    web = FakeWebProcessor(tmp_path, fail_lotes={"L001"})
    performer = LotePerformer(
        queue,
        {"L001", "L002"},
        VaultClient(FakeVaultProvider()),
        web_processor=web,
    )

    result = performer.run()

    assert result.total == 2
    assert result.system_errors == 1
    assert result.success == 1
    assert web.error_captures == ["L001"]
    assert queue.system_errors[0][2]["resultado_validacao"] == "ERRO"
    assert queue.system_errors[0][2]["evidencia"] == "artefatos/erro-L001.png"
    assert queue.done[0][0]["lote_id"] == "L002"


def test_performer_isola_falha_inesperada_na_classificacao_e_continua():
    class ClassificationFailurePerformer(LotePerformer):
        def _classify(self, current_item):
            if current_item["lote_id"] == "L001":
                raise RuntimeError("classificador indisponível")
            return super()._classify(current_item)

    queue = FakeQueue([item(lote_id="L001"), item(lote_id="L002")])
    performer = ClassificationFailurePerformer(
        queue,
        {"L001", "L002"},
        VaultClient(FakeVaultProvider()),
    )

    result = performer.run()

    assert result.total == 2
    assert result.system_errors == 1
    assert result.success == 1
    assert queue.system_errors[0][0]["lote_id"] == "L001"
    assert queue.system_errors[0][2]["resultado_validacao"] == "ERRO"
    assert queue.done[0][0]["lote_id"] == "L002"


def test_performer_isola_falha_na_finalizacao_e_continua_proximo_item():
    class FinalizationFailureQueue(FakeQueue):
        def mark_done(self, current_item, output):
            if current_item["lote_id"] == "L001":
                raise RuntimeError("DataPool recusou finalização")
            super().mark_done(current_item, output)

    queue = FinalizationFailureQueue(
        [item(lote_id="L001"), item(lote_id="L002")]
    )
    performer = LotePerformer(
        queue,
        {"L001", "L002"},
        VaultClient(FakeVaultProvider()),
    )

    result = performer.run()

    assert result.total == 2
    assert result.system_errors == 1
    assert result.success == 1
    assert queue.system_errors[0][0]["lote_id"] == "L001"
    assert queue.done[0][0]["lote_id"] == "L002"


def test_performer_continua_se_registro_do_erro_de_sistema_tambem_falhar():
    class UnavailableFinalizationQueue(FakeQueue):
        def mark_done(self, current_item, output):
            if current_item["lote_id"] == "L001":
                raise RuntimeError("falha na conclusão")
            super().mark_done(current_item, output)

        def mark_system_error(self, current_item, error, output):
            raise RuntimeError("falha ao registrar erro")

    queue = UnavailableFinalizationQueue(
        [item(lote_id="L001"), item(lote_id="L002")]
    )
    performer = LotePerformer(
        queue,
        {"L001", "L002"},
        VaultClient(FakeVaultProvider()),
    )

    result = performer.run()

    assert result.total == 2
    assert result.system_errors == 1
    assert result.success == 1
    assert queue.done[0][0]["lote_id"] == "L002"
