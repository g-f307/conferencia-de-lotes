from pathlib import Path

import pytest

from src.config import Settings, as_bool, botcity_runner_args


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("SIM", True), ("1", True), ("false", False), (None, False)],
)
def test_as_bool(value, expected):
    assert as_bool(value) is expected


def test_settings_resolve_caminhos_relativos(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("INPUT_DIR", "entrada_teste")
    monkeypatch.setenv("INPUT_CSV", "entrada_teste/lotes.csv")
    monkeypatch.setenv("LOG_FILE", "saida/teste.log")
    settings = Settings.from_env(tmp_path)
    assert settings.input_dir == tmp_path / "entrada_teste"
    assert settings.input_csv == tmp_path / "entrada_teste" / "lotes.csv"
    assert settings.log_file == tmp_path / "saida/teste.log"


def test_settings_nao_contem_senha_do_erp(tmp_path: Path):
    settings = Settings.from_env(tmp_path)
    assert not hasattr(settings, "erp_password")
    assert not hasattr(settings, "password")


def test_maestro_desativado_nao_exige_chaves(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MAESTRO_ENABLED", "false")
    Settings.from_env(tmp_path).validate()


def test_settings_carrega_maestro_task_id(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MAESTRO_TASK_ID", "123")

    settings = Settings.from_env(tmp_path)

    assert settings.maestro_task_id == "123"


def test_settings_carrega_identificadores_de_log(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BOT_ID", "auditor-lotes")
    monkeypatch.setenv("EXECUTION_ID", "exec-123")

    settings = Settings.from_env(tmp_path)

    assert settings.bot_id == "auditor-lotes"
    assert settings.execution_id == "exec-123"


def test_settings_usa_identificadores_locais_padrao(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("BOT_ID", raising=False)
    monkeypatch.delenv("EXECUTION_ID", raising=False)
    monkeypatch.setattr("sys.argv", ["bot.py"])

    settings = Settings.from_env(tmp_path)

    assert settings.bot_id == "bot-conferencia-de-lotes-v1"
    assert settings.execution_id == "execucao-local"


def test_settings_usa_task_id_do_runner_como_execution_id(
    monkeypatch, tmp_path: Path
):
    monkeypatch.delenv("EXECUTION_ID", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        ["bot.py", "https://maestro.example", "task-456", "token"],
    )

    settings = Settings.from_env(tmp_path)

    assert settings.execution_id == "task-456"


def test_botcity_runner_args_reconhece_server_e_task_id():
    assert botcity_runner_args(["bot.py", "https://maestro.example", "123", "token"]) == (
        "https://maestro.example",
        "123",
    )


def test_settings_usa_contexto_do_runner_sem_chaves_tecnicas(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("MAESTRO_ENABLED", raising=False)
    monkeypatch.delenv("VAULT_ENABLED", raising=False)
    monkeypatch.delenv("MAESTRO_SERVER", raising=False)
    monkeypatch.delenv("MAESTRO_LOGIN", raising=False)
    monkeypatch.delenv("MAESTRO_KEY", raising=False)
    monkeypatch.delenv("MAESTRO_TASK_ID", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        ["bot.py", "https://maestro.example", "23831639", "token"],
    )

    settings = Settings.from_env(tmp_path)

    assert settings.runner_context is True
    assert settings.maestro_enabled is True
    assert settings.vault_enabled is True
    assert settings.maestro_server == "https://maestro.example"
    assert settings.maestro_task_id == "23831639"
    settings.validate()


def test_settings_ignora_maestro_task_id_vazio_quando_runner_informa_task(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("MAESTRO_TASK_ID", "")
    monkeypatch.setattr(
        "sys.argv",
        ["bot.py", "https://maestro.example", "23831639", "token"],
    )

    settings = Settings.from_env(tmp_path)

    assert settings.maestro_task_id == "23831639"


def test_settings_carrega_lotes_de_referencia(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("REFERENCE_LOTES", "L010, L011,,L012")

    settings = Settings.from_env(tmp_path)

    assert settings.reference_lotes == ("L010", "L011", "L012")


def test_settings_carrega_delay_de_processamento(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PROCESSING_DELAY_SECONDS", "0.25")

    settings = Settings.from_env(tmp_path)

    assert settings.processing_delay_seconds == 0.25


def test_settings_carrega_configuracao_da_automacao_web(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("WEB_AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("WEB_TEST_URL", "docs/index-lotes/index.html")

    settings = Settings.from_env(tmp_path)

    assert settings.web_automation_enabled is True
    assert settings.web_test_url == "docs/index-lotes/index.html"
    assert settings.web_artifact_dir == tmp_path / "artefatos"


def test_maestro_ativado_exige_chaves(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MAESTRO_ENABLED", "true")
    monkeypatch.delenv("MAESTRO_SERVER", raising=False)
    monkeypatch.delenv("MAESTRO_LOGIN", raising=False)
    monkeypatch.delenv("MAESTRO_KEY", raising=False)
    with pytest.raises(ValueError, match="Configuração obrigatória ausente"):
        Settings.from_env(tmp_path).validate()


def test_maestro_ativado_exige_vault(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MAESTRO_ENABLED", "true")
    monkeypatch.setenv("MAESTRO_SERVER", "https://maestro.example")
    monkeypatch.setenv("MAESTRO_LOGIN", "login")
    monkeypatch.setenv("MAESTRO_KEY", "key")
    monkeypatch.setenv("VAULT_ENABLED", "false")
    with pytest.raises(ValueError, match="VAULT_ENABLED"):
        Settings.from_env(tmp_path).validate()
