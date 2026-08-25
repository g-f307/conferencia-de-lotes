from dataclasses import replace
from pathlib import Path

import pytest

from src.config import (
    Settings,
    as_bool,
    as_optional_float,
    botcity_runner_args,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("SIM", True), ("1", True), ("false", False), (None, False)],
)
def test_as_bool(value, expected):
    assert as_bool(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 15.0),
        ("20", 20.0),
        ("2.5", 2.5),
        ("", None),
        ("abc", None),
        ("nan", None),
        ("inf", None),
    ],
)
def test_as_optional_float(value, expected):
    assert as_optional_float(value, 15.0) == expected


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
    monkeypatch.setenv("WEB_AUTOMATION_ENABLED", "false")
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

    assert settings.bot_id == "bot-conferencia-de-lotes-v2"
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
    page = tmp_path / "web" / "index-lotes" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("<html></html>", encoding="utf-8")
    monkeypatch.delenv("MAESTRO_ENABLED", raising=False)
    monkeypatch.delenv("VAULT_ENABLED", raising=False)
    monkeypatch.delenv("MAESTRO_SERVER", raising=False)
    monkeypatch.delenv("MAESTRO_LOGIN", raising=False)
    monkeypatch.delenv("MAESTRO_KEY", raising=False)
    monkeypatch.delenv("MAESTRO_TASK_ID", raising=False)
    monkeypatch.delenv("WEB_TEST_URL", raising=False)
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


def test_settings_habilita_automacao_web_por_padrao_no_runner(
    monkeypatch,
    tmp_path: Path,
):
    page = tmp_path / "web" / "index-lotes" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("<html></html>", encoding="utf-8")
    monkeypatch.delenv("WEB_AUTOMATION_ENABLED", raising=False)
    monkeypatch.delenv("WEB_TEST_URL", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        ["bot.py", "https://maestro.example", "23831639", "token"],
    )

    settings = Settings.from_env(tmp_path)

    assert settings.web_automation_enabled is True
    settings.validate()


def test_settings_permite_desabilitar_automacao_web_no_runner(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("WEB_AUTOMATION_ENABLED", "false")
    monkeypatch.setattr(
        "sys.argv",
        ["bot.py", "https://maestro.example", "23831639", "token"],
    )

    settings = Settings.from_env(tmp_path)

    assert settings.web_automation_enabled is False
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
    monkeypatch.setenv("WEB_TEST_URL", "web/index-lotes/index.html")
    monkeypatch.setenv("WEB_TIMEOUT_SECONDS", "20")

    settings = Settings.from_env(tmp_path)

    assert settings.web_automation_enabled is True
    assert settings.web_test_url == "web/index-lotes/index.html"
    assert settings.web_artifact_dir == tmp_path / "artefatos"
    assert settings.web_timeout_seconds == 20


def test_settings_valida_url_web_local_quando_playwright_habilitado(
    monkeypatch, tmp_path: Path
):
    page = tmp_path / "web" / "index-lotes" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("WEB_AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("WEB_TEST_URL", "web/index-lotes/index.html")

    Settings.from_env(tmp_path).validate()


def test_settings_rejeita_url_web_local_inexistente_quando_playwright_habilitado(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("WEB_AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("WEB_TEST_URL", "web/index-lotes/index.html")

    with pytest.raises(ValueError, match="WEB_TEST_URL local inexistente"):
        Settings.from_env(tmp_path).validate()


def test_settings_rejeita_timeout_web_invalido(monkeypatch, tmp_path: Path):
    page = tmp_path / "web" / "index-lotes" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("WEB_AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("WEB_TIMEOUT_SECONDS", "0")

    with pytest.raises(ValueError, match="WEB_TIMEOUT_SECONDS"):
        Settings.from_env(tmp_path).validate()


@pytest.mark.parametrize("invalid_timeout", ["", "abc"])
def test_settings_rejeita_timeout_web_nao_numerico_no_validate(
    monkeypatch,
    tmp_path: Path,
    invalid_timeout: str,
):
    page = tmp_path / "web" / "index-lotes" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("WEB_AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("WEB_TEST_URL", "web/index-lotes/index.html")
    monkeypatch.setenv("WEB_TIMEOUT_SECONDS", invalid_timeout)

    settings = Settings.from_env(tmp_path)

    assert settings.web_timeout_seconds is None
    with pytest.raises(
        ValueError,
        match="WEB_TIMEOUT_SECONDS deve ser um número maior que zero",
    ):
        settings.validate()


def test_settings_ignora_timeout_web_invalido_quando_automacao_desabilitada(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("WEB_AUTOMATION_ENABLED", "false")
    monkeypatch.setenv("WEB_TIMEOUT_SECONDS", "invalido")

    settings = Settings.from_env(tmp_path)

    assert settings.web_timeout_seconds is None
    settings.validate()


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


def test_settings_mantem_ml_desabilitado_por_padrao(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ML_ENABLED", raising=False)
    monkeypatch.delenv("ML_API_URL", raising=False)
    monkeypatch.delenv("ML_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ML_CONFIANCA_MINIMA", raising=False)

    settings = Settings.from_env(tmp_path)

    assert settings.ml_enabled is False
    assert settings.ml_api_url == ""
    assert settings.ml_timeout_seconds == 3
    assert settings.ml_confianca_minima == 0.85
    settings.validate()


def test_settings_carrega_e_valida_integracao_ml(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ML_ENABLED", "true")
    monkeypatch.setenv("ML_API_URL", "http://api-ml:8000")
    monkeypatch.setenv("ML_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("ML_CONFIANCA_MINIMA", "0.72")

    settings = Settings.from_env(tmp_path)

    assert settings.ml_enabled is True
    assert settings.ml_api_url == "http://api-ml:8000"
    assert settings.ml_timeout_seconds == 2.5
    assert settings.ml_confianca_minima == 0.72
    settings.validate()


@pytest.mark.parametrize("invalid_confidence", ["-0.1", "1.1", "abc", ""])
def test_settings_rejeita_confianca_ml_invalida_quando_habilitado(
    monkeypatch,
    tmp_path: Path,
    invalid_confidence: str,
):
    monkeypatch.setenv("ML_ENABLED", "true")
    monkeypatch.setenv("ML_API_URL", "http://api-ml:8000")
    monkeypatch.setenv("ML_CONFIANCA_MINIMA", invalid_confidence)

    with pytest.raises(ValueError, match="ML_CONFIANCA_MINIMA"):
        Settings.from_env(tmp_path).validate()


def test_settings_exige_url_quando_ml_esta_habilitado(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ML_ENABLED", "true")
    monkeypatch.setenv("ML_API_URL", "")

    with pytest.raises(ValueError, match="ML_API_URL deve ser informado"):
        Settings.from_env(tmp_path).validate()


@pytest.mark.parametrize("invalid_url", ["api-ml:8000", "ftp://api-ml/modelo"])
def test_settings_rejeita_url_ml_invalida(
    monkeypatch,
    tmp_path: Path,
    invalid_url: str,
):
    monkeypatch.setenv("ML_ENABLED", "true")
    monkeypatch.setenv("ML_API_URL", invalid_url)

    with pytest.raises(ValueError, match="URL HTTP ou HTTPS válida"):
        Settings.from_env(tmp_path).validate()


@pytest.mark.parametrize(
    "sensitive_url",
    [
        "http://usuario:senha@api-ml:8000",
        "http://api-ml:8000?token=ficticio",
    ],
)
def test_settings_rejeita_credencial_ou_parametro_na_url_ml(
    monkeypatch,
    tmp_path: Path,
    sensitive_url: str,
):
    monkeypatch.setenv("ML_ENABLED", "true")
    monkeypatch.setenv("ML_API_URL", sensitive_url)

    with pytest.raises(ValueError, match="não deve conter credenciais"):
        Settings.from_env(tmp_path).validate()


@pytest.mark.parametrize("invalid_timeout", ["0", "-1", "abc", ""])
def test_settings_rejeita_timeout_ml_invalido_quando_habilitado(
    monkeypatch,
    tmp_path: Path,
    invalid_timeout: str,
):
    monkeypatch.setenv("ML_ENABLED", "true")
    monkeypatch.setenv("ML_API_URL", "http://api-ml:8000")
    monkeypatch.setenv("ML_TIMEOUT_SECONDS", invalid_timeout)

    with pytest.raises(ValueError, match="ML_TIMEOUT_SECONDS"):
        Settings.from_env(tmp_path).validate()


def test_settings_ignora_configuracao_ml_invalida_quando_desabilitado(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("ML_ENABLED", "false")
    monkeypatch.setenv("ML_API_URL", "invalida")
    monkeypatch.setenv("ML_TIMEOUT_SECONDS", "invalido")

    Settings.from_env(tmp_path).validate()


def test_settings_carrega_configuracao_de_orquestracao(monkeypatch, tmp_path):
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("ORCHESTRATION_POLL_INTERVAL_SECONDS", "0.5")

    settings = Settings.from_env(tmp_path)

    assert settings.orchestration_enabled is True
    assert settings.orchestration_timeout_seconds == 120
    assert settings.orchestration_poll_interval_seconds == 0.5


def test_orquestracao_habilitada_exige_maestro(tmp_path):
    settings = Settings.from_env(tmp_path)

    with pytest.raises(ValueError, match="MAESTRO_ENABLED.*ORCHESTRATION_ENABLED"):
        replace(settings, orchestration_enabled=True).validate()


@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        (
            "orchestration_timeout_seconds",
            0,
            "ORCHESTRATION_TIMEOUT_SECONDS",
        ),
        (
            "orchestration_poll_interval_seconds",
            None,
            "ORCHESTRATION_POLL_INTERVAL_SECONDS",
        ),
    ],
)
def test_settings_rejeita_tempos_invalidos_da_orquestracao(
    tmp_path,
    field_name,
    field_value,
    message,
):
    settings = replace(
        Settings.from_env(tmp_path),
        orchestration_enabled=True,
        maestro_enabled=True,
        vault_enabled=True,
        maestro_server="https://maestro.example",
        maestro_login="login",
        maestro_key="key",
    )

    with pytest.raises(ValueError, match=message):
        replace(settings, **{field_name: field_value}).validate()


def test_settings_carrega_configuracao_de_resiliencia(monkeypatch, tmp_path):
    monkeypatch.setenv("REFERENCE_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("REFERENCE_RETRY_BASE_INTERVAL_SECONDS", "1.5")
    monkeypatch.setenv("REFERENCE_TIMEOUT_SECONDS", "8")
    monkeypatch.setenv("DEAD_LETTER_PATH", "saida/dead-letter.jsonl")

    settings = Settings.from_env(tmp_path)

    assert settings.reference_max_attempts == 4
    assert settings.reference_retry_base_interval_seconds == 1.5
    assert settings.reference_timeout_seconds == 8
    assert settings.dead_letter_path == (tmp_path / "saida/dead-letter.jsonl").resolve()


@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        ("reference_max_attempts", 0, "REFERENCE_MAX_ATTEMPTS"),
        (
            "reference_retry_base_interval_seconds",
            None,
            "REFERENCE_RETRY_BASE_INTERVAL_SECONDS",
        ),
        ("reference_timeout_seconds", -1, "REFERENCE_TIMEOUT_SECONDS"),
        ("dead_letter_path", None, "DEAD_LETTER_PATH"),
    ],
)
def test_settings_rejeita_configuracao_de_resiliencia_invalida(
    tmp_path,
    field_name,
    field_value,
    message,
):
    settings = Settings.from_env(tmp_path)

    with pytest.raises(ValueError, match=message):
        replace(settings, **{field_name: field_value}).validate()
