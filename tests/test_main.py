import json
from dataclasses import replace

from src.config import Settings
from src.logging_config import configure_logging
from src.main import run, save_execution_report
from src.models import ExecutionResult
from src.vault_client import VaultClient


class FakeAlertGateway:
    def __init__(self):
        self.messages: list[str] = []

    def send_error_alert(self, message: str) -> None:
        self.messages.append(message)


class FakeMaestroClient:
    def __init__(self, items):
        self.items = list(items)
        self.info_alerts = []
        self.error_alerts = []
        self.done = []
        self.business_errors = []
        self.system_errors = []
        self.human_reviews = []
        self.artifacts = []
        self.finished_tasks = []

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

    def send_start_alert(self):
        self.info_alerts.append("Iniciando auditoria de acessos")

    def send_error_alert(self, message):
        self.error_alerts.append(message)

    def post_summary_artifact(self, summary, report_dir=None, artifact_name="resumo_execucao.json"):
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / artifact_name
        path.write_text(json.dumps(summary), encoding="utf-8")
        self.artifacts.append((artifact_name, path, summary))
        return path

    def finish_task(self, status, message, total_items, processed_items, failed_items):
        self.finished_tasks.append(
            (status, message, total_items, processed_items, failed_items)
        )

    def create_entry(self, data):
        self.items.append(data)


class BrokenNextMaestroClient(FakeMaestroClient):
    def has_next(self):
        return True

    def next(self):
        raise RuntimeError("DataPool indisponivel")


class FakeVaultProvider:
    def get_credential(self, label):
        return {"username": "marcelo.erp", "password": "fake-password"}


class BrokenVaultProvider:
    def get_credential(self, label):
        raise RuntimeError(f"Credencial {label} nao contem username")


def lote_item(**overrides):
    item = {
        "lote_id": "L001",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manha",
        "status": "APROVADO",
        "responsavel": "Marcelo",
        "data": "2026-07-20",
        "observacao": "",
    }
    item.update(overrides)
    return item


def settings_for(tmp_path, input_exists=True):
    settings = Settings.from_env(tmp_path)
    if input_exists:
        settings.input_dir.mkdir(parents=True)
        settings.input_csv.write_text(
            "lote_id,produto,linha,turno,status,responsavel,data,observacao\n",
            encoding="utf-8",
        )
    return replace(settings, processing_delay_seconds=0)


def test_fail_fast_quando_pasta_de_entrada_nao_existe(tmp_path):
    settings = settings_for(tmp_path, input_exists=False)
    gateway = FakeAlertGateway()
    result = run(settings=settings, alert_gateway=gateway)
    assert result.status == "FAILED"
    assert "inexistente" in result.message
    assert gateway.messages == [result.message]


def test_fail_fast_maestro_habilitado_cria_gateway_para_alerta(monkeypatch, tmp_path):
    settings = replace(
        settings_for(tmp_path, input_exists=False),
        maestro_enabled=True,
        vault_enabled=True,
        maestro_server="https://maestro.example",
        maestro_login="login",
        maestro_key="key",
    )
    created = []

    class Client(FakeAlertGateway):
        def __init__(self, received_settings):
            super().__init__()
            self.received_settings = received_settings
            created.append(self)

    monkeypatch.setattr("src.main.MaestroClient", Client)

    result = run(settings=settings)

    assert result.status == "FAILED"
    assert created[0].received_settings == settings
    assert created[0].messages == [result.message]


def test_execucao_local_valida_estrutura(tmp_path):
    settings = settings_for(tmp_path)
    result = run(settings=settings)
    assert result.status == "SUCCESS"
    assert result.finished_at is not None


def test_log_contem_data_severidade_e_mensagem(tmp_path):
    log_file = tmp_path / "logs" / "execucao.log"
    logger = configure_logging(log_file)
    logger.warning("mensagem de teste")
    content = log_file.read_text(encoding="utf-8")
    assert "WARNING" in content
    assert "mensagem de teste" in content
    assert "20" in content


def test_relatorio_json_serializa_execution_result(tmp_path):
    result = ExecutionResult(total_items=2, processed_items=1, failed_items=1)
    result.complete()
    path = save_execution_report(result, tmp_path / "relatorios")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "PARTIALLY_COMPLETED"
    assert payload["total_items"] == 2


def test_configuracao_invalida_falha_antes_do_processamento(tmp_path):
    settings = replace(
        settings_for(tmp_path),
        maestro_enabled=True,
        vault_enabled=False,
        maestro_server="server",
        maestro_login="login",
        maestro_key="key",
    )
    result = run(settings=settings)
    assert result.status == "FAILED"
    assert "VAULT_ENABLED" in result.message


def test_run_consumindo_datapool_e_publicando_resumo(tmp_path):
    settings = settings_for(tmp_path)
    settings.input_csv.write_text(
        "lote_id,produto,linha,turno,status,responsavel,data,observacao\n"
        "L001,Monitor,Linha A,Manha,APROVADO,Marcelo,2026-07-20,\n"
        "L999,Monitor,Linha A,Manha,APROVADO,Marcelo,2026-07-20,\n"
        "L001,Monitor,Linha A,Manha,pendente,Marcelo,2026-07-20,\n",
        encoding="utf-8",
    )
    client = FakeMaestroClient([])
    vault = VaultClient(FakeVaultProvider())

    result = run(
        settings=settings,
        maestro_client=client,
        vault_client=vault,
        reference_lotes={"L001"},
    )

    assert result.status == "PARTIALLY_COMPLETED"
    assert result.total_items == 3
    assert result.processed_items == 1
    assert result.failed_items == 1
    assert result.ambiguous_items == 1
    assert client.info_alerts == ["Iniciando auditoria de acessos"]
    assert len(client.done) == 1
    assert len(client.business_errors) == 1
    assert len(client.human_reviews) == 1
    assert client.artifacts[0][0] == "resumo_execucao.json"
    assert client.artifacts[0][2]["total_items"] == 3
    assert client.finished_tasks[0][0] == "SUCCESS"
    assert client.finished_tasks[0][2:] == (3, 1, 2)


def test_run_falha_quando_next_da_fila_quebra(tmp_path):
    settings = settings_for(tmp_path)
    client = BrokenNextMaestroClient([])
    vault = VaultClient(FakeVaultProvider())

    result = run(settings=settings, maestro_client=client, vault_client=vault)

    assert result.status == "FAILED"
    assert "Falha tecnica ao obter item da fila" in result.message
    assert client.system_errors == []
    assert client.finished_tasks[0][0] == "FAILED"


def test_run_falha_sem_publicar_csv_quando_vault_esta_invalido(tmp_path):
    settings = settings_for(tmp_path)
    settings.input_csv.write_text(
        "lote_id,produto,linha,turno,status,responsavel,data,observacao\n"
        "L001,Monitor,Linha A,Manha,APROVADO,Marcelo,2026-07-20,\n",
        encoding="utf-8",
    )
    client = FakeMaestroClient([])
    vault = VaultClient(BrokenVaultProvider(), "credencial_erp2")

    result = run(settings=settings, maestro_client=client, vault_client=vault)

    assert result.status == "FAILED"
    assert "credencial_erp2" in result.message
    assert client.items == []
    assert client.finished_tasks[0][0] == "FAILED"


def test_run_executa_automacao_web_quando_habilitada(monkeypatch, tmp_path):
    settings = replace(
        settings_for(tmp_path),
        web_automation_enabled=True,
        web_test_url="docs/index-lotes/index.html",
    )
    client = FakeMaestroClient([])
    vault = VaultClient(FakeVaultProvider())
    calls = []

    def fake_run_web_automation(url, base_dir):
        calls.append((url, base_dir))
        return (base_dir / url).as_uri()

    monkeypatch.setattr(
        "src.main.run_web_automation", fake_run_web_automation
    )

    result = run(
        settings=settings,
        maestro_client=client,
        vault_client=vault,
    )

    assert result.status == "SUCCESS"
    assert calls == [
        ("docs/index-lotes/index.html", settings.base_dir)
    ]
