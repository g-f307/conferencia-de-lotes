import json
from dataclasses import replace

from src.config import Settings
from src.logging_config import configure_logging
from src.main import run, save_execution_report
from src.models import ExecutionResult


class FakeAlertGateway:
    def __init__(self):
        self.messages: list[str] = []

    def send_error_alert(self, message: str) -> None:
        self.messages.append(message)


def settings_for(tmp_path, input_exists=True):
    settings = Settings.from_env(tmp_path)
    if input_exists:
        settings.input_dir.mkdir(parents=True)
    return settings


def test_fail_fast_quando_pasta_de_entrada_nao_existe(tmp_path):
    settings = settings_for(tmp_path, input_exists=False)
    gateway = FakeAlertGateway()
    result = run(settings=settings, alert_gateway=gateway)
    assert result.status == "FAILED"
    assert "inexistente" in result.message
    assert gateway.messages == [result.message]


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
