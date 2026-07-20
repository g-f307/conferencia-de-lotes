import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.dispatcher import DATAPOOL_FIELDS, dispatch_csv, iter_csv_rows
from src.maestro_client import BotCityMaestroGateway, MaestroClient
from src.validation import HumanReviewRequired


class FakeGateway:
    def __init__(self):
        self.created = []
        self.queue = []
        self.alerts = []
        self.info_alerts = []
        self.artifacts = []
        self.done = []
        self.business_errors = []
        self.system_errors = []
        self.human_reviews = []

    def create_datapool_entry(self, datapool_label, data):
        self.created.append((datapool_label, data))
        self.queue.append(data)

    def has_next(self, datapool_label):
        return bool(self.queue)

    def next(self, datapool_label):
        return self.queue.pop(0)

    def send_error_alert(self, message):
        self.alerts.append(message)

    def send_info_alert(self, message):
        self.info_alerts.append(message)

    def post_artifact(self, name, path):
        self.artifacts.append((name, path))

    def mark_done(self, item, result):
        self.done.append((item, result))

    def mark_business_error(self, item, error):
        self.business_errors.append((item, error))

    def mark_system_error(self, item, error):
        self.system_errors.append((item, error))

    def mark_human_review(self, item, review):
        self.human_reviews.append((item, review))


def settings_for(tmp_path):
    return Settings.from_env(tmp_path)


def write_csv(tmp_path, content):
    path = tmp_path / "lotes.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_dispatcher_publica_uma_entrada_por_linha_no_datapool(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "lote_id,produto,linha,turno,status,responsavel,data,observacao\n"
        "LG-1,TV,L1,A,APROVADO,Ana,14/06/2026,\n"
        "LG-2,MON,L2,B,NOK,Bruno,14/06/2026,Defeito\n",
    )
    gateway = FakeGateway()
    client = MaestroClient(settings_for(tmp_path), gateway=gateway)

    published = dispatch_csv(csv_path, client, logger=logging.getLogger("test"))

    assert published == 2
    assert [entry[0] for entry in gateway.created] == [
        "FilaAuditoriaLotes",
        "FilaAuditoriaLotes",
    ]
    assert gateway.created[0][1] == {
        "lote_id": "LG-1",
        "produto": "TV",
        "linha": "L1",
        "turno": "A",
        "status": "APROVADO",
        "responsavel": "Ana",
        "data": "14/06/2026",
        "observacao": "",
    }


def test_dispatcher_usa_cabecalho_sem_posicoes_magicas(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "status,observacao,data,responsavel,turno,linha,produto,lote_id\n"
        "PENDENTE,Aguardando,14/06/2026,Carlos,C,L3,AC,LG-3\n",
    )

    rows = list(iter_csv_rows(csv_path))

    assert rows == [
        {
            "lote_id": "LG-3",
            "produto": "AC",
            "linha": "L3",
            "turno": "C",
            "status": "PENDENTE",
            "responsavel": "Carlos",
            "data": "14/06/2026",
            "observacao": "Aguardando",
        }
    ]


def test_dispatcher_exige_campos_para_publicar_no_datapool(tmp_path):
    csv_path = write_csv(tmp_path, "lote_id,produto\nLG-1,TV\n")

    with pytest.raises(ValueError) as exc:
        list(iter_csv_rows(csv_path))

    assert "linha" in str(exc.value)


def test_maestro_client_expoe_has_next_e_next(tmp_path):
    gateway = FakeGateway()
    client = MaestroClient(settings_for(tmp_path), gateway=gateway)
    item = {field: f"valor_{field}" for field in DATAPOOL_FIELDS}

    client.create_entry(item)

    assert client.has_next() is True
    assert client.next() == item
    assert client.has_next() is False


def test_maestro_client_envia_alerta_de_pasta_ausente(tmp_path):
    gateway = FakeGateway()
    client = MaestroClient(settings_for(tmp_path), gateway=gateway)

    client.send_error_alert("Pasta de entrada inexistente")

    assert gateway.alerts == ["Pasta de entrada inexistente"]


def test_maestro_client_envia_alerta_inicial(tmp_path):
    gateway = FakeGateway()
    client = MaestroClient(settings_for(tmp_path), gateway=gateway)

    client.send_start_alert()

    assert gateway.info_alerts == ["Iniciando auditoria de acessos"]
    assert gateway.alerts == []


def test_maestro_client_publica_resumo_json_como_artefato(tmp_path):
    gateway = FakeGateway()
    client = MaestroClient(settings_for(tmp_path), gateway=gateway)

    artifact_path = client.post_summary_artifact(
        {"total_items": 2, "status": "SUCCESS"},
        report_dir=tmp_path / "relatorios",
    )

    assert artifact_path.exists()
    assert '"total_items": 2' in artifact_path.read_text(encoding="utf-8")
    assert gateway.artifacts == [("resumo_execucao.json", artifact_path)]


def test_maestro_client_usa_gateway_real_quando_maestro_esta_habilitado(tmp_path):
    settings = replace(
        settings_for(tmp_path),
        maestro_enabled=True,
        vault_enabled=True,
        maestro_server="https://maestro.example",
        maestro_login="login",
        maestro_key="key",
    )
    created_with = []

    def factory(received_settings):
        created_with.append(received_settings)
        return FakeGateway()

    client = MaestroClient(settings, real_gateway_factory=factory)

    assert created_with == [settings]
    assert isinstance(client.gateway, FakeGateway)


def test_maestro_client_maestro_habilitado_chama_factory_real_padrao(tmp_path, monkeypatch):
    settings = replace(
        settings_for(tmp_path),
        maestro_enabled=True,
        vault_enabled=True,
        maestro_server="https://maestro.example",
        maestro_login="login",
        maestro_key="key",
    )
    created_with = []

    def fake_from_settings(received_settings):
        created_with.append(received_settings)
        return FakeGateway()

    monkeypatch.setattr(BotCityMaestroGateway, "from_settings", fake_from_settings)

    client = MaestroClient(settings)

    assert created_with == [settings]
    assert isinstance(client.gateway, FakeGateway)


class FakeDataPoolEntry:
    def __init__(self, values):
        self.values = values
        self.done_messages = []
        self.error_reports = []

    def report_done(self, finish_message=""):
        self.done_messages.append(finish_message)

    def report_error(self, error_type=None, finish_message=""):
        self.error_reports.append((error_type, finish_message))


class FakeDataPool:
    def __init__(self):
        self.created_entries = []
        self.next_calls = []
        self.next_item = FakeDataPoolEntry({"lote_id": "LG-1"})

    def create_entry(self, entry):
        self.created_entries.append(entry)
        return entry

    def has_next(self):
        return True

    def next(self, task_id=None):
        self.next_calls.append(task_id)
        return self.next_item


class FakeSdk:
    def __init__(self):
        self.task_id = 123
        self.datapool = FakeDataPool()
        self.datapool_labels = []
        self.alerts = []
        self.artifacts = []

    def get_datapool(self, label):
        self.datapool_labels.append(label)
        return self.datapool

    def alert(self, task_id, title, message, alert_type):
        self.alerts.append((task_id, title, message, alert_type))

    def post_artifact(self, task_id, artifact_name, filepath):
        self.artifacts.append((task_id, artifact_name, filepath))


def test_gateway_real_publica_item_com_datapool_entry():
    sdk = FakeSdk()
    error_type = SimpleNamespace(BUSINESS="BUSINESS", SYSTEM="SYSTEM")
    alert_type = SimpleNamespace(INFO="INFO", ERROR="ERROR")
    gateway = BotCityMaestroGateway(sdk, FakeDataPoolEntry, error_type, alert_type)

    gateway.create_datapool_entry("FilaAuditoriaLotes", {"lote_id": "LG-1"})

    assert sdk.datapool_labels == ["FilaAuditoriaLotes"]
    assert sdk.datapool.created_entries[0].values == {"lote_id": "LG-1"}


def test_gateway_real_consume_item_com_task_id():
    sdk = FakeSdk()
    error_type = SimpleNamespace(BUSINESS="BUSINESS", SYSTEM="SYSTEM")
    alert_type = SimpleNamespace(INFO="INFO", ERROR="ERROR")
    gateway = BotCityMaestroGateway(sdk, FakeDataPoolEntry, error_type, alert_type)

    assert gateway.has_next("FilaAuditoriaLotes") is True
    item = gateway.next("FilaAuditoriaLotes")

    assert item is sdk.datapool.next_item
    assert sdk.datapool.next_calls == [123]


def test_gateway_real_finaliza_itens_com_done_e_erros():
    sdk = FakeSdk()
    error_type = SimpleNamespace(BUSINESS="BUSINESS", SYSTEM="SYSTEM")
    alert_type = SimpleNamespace(INFO="INFO", ERROR="ERROR")
    gateway = BotCityMaestroGateway(sdk, FakeDataPoolEntry, error_type, alert_type)
    item = FakeDataPoolEntry({"lote_id": "LG-1"})

    gateway.mark_done(item, {"status": "APROVADO"})
    gateway.mark_business_error(item, "campo obrigatorio vazio")
    gateway.mark_system_error(item, "Maestro indisponivel")
    gateway.mark_human_review(
        item,
        HumanReviewRequired(lote_id="LG-1", status_original="EM ANALISE"),
    )

    assert item.done_messages == ["Lote processado com sucesso"]
    assert item.error_reports == [
        ("BUSINESS", "campo obrigatorio vazio"),
        ("SYSTEM", "Maestro indisponivel"),
        ("BUSINESS", "Status ambiguo separado para revisao humana"),
    ]


def test_gateway_real_emite_alerta_info_erro_e_artefato(tmp_path):
    sdk = FakeSdk()
    error_type = SimpleNamespace(BUSINESS="BUSINESS", SYSTEM="SYSTEM")
    alert_type = SimpleNamespace(INFO="INFO", ERROR="ERROR")
    gateway = BotCityMaestroGateway(sdk, FakeDataPoolEntry, error_type, alert_type)
    artifact = tmp_path / "resumo_execucao.json"

    gateway.send_info_alert("Iniciando auditoria de acessos")
    gateway.send_error_alert("Pasta de entrada inexistente")
    gateway.post_artifact("resumo_execucao.json", artifact)

    assert sdk.alerts == [
        (123, "Auditoria de lotes", "Iniciando auditoria de acessos", "INFO"),
        (123, "Auditoria de lotes", "Pasta de entrada inexistente", "ERROR"),
    ]
    assert sdk.artifacts == [(123, "resumo_execucao.json", str(artifact))]
