import logging

import pytest

from src.config import Settings
from src.dispatcher import DATAPOOL_FIELDS, dispatch_csv, iter_csv_rows
from src.maestro_client import MaestroClient


class FakeGateway:
    def __init__(self):
        self.created = []
        self.queue = []
        self.alerts = []
        self.artifacts = []

    def create_datapool_entry(self, datapool_label, data):
        self.created.append((datapool_label, data))
        self.queue.append(data)

    def has_next(self, datapool_label):
        return bool(self.queue)

    def next(self, datapool_label):
        return self.queue.pop(0)

    def send_error_alert(self, message):
        self.alerts.append(message)

    def post_artifact(self, name, path):
        self.artifacts.append((name, path))


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

    assert gateway.alerts == ["Iniciando auditoria de acessos"]


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
