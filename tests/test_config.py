from pathlib import Path

import pytest

from src.config import Settings, as_bool


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("SIM", True), ("1", True), ("false", False), (None, False)],
)
def test_as_bool(value, expected):
    assert as_bool(value) is expected


def test_settings_resolve_caminhos_relativos(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("INPUT_DIR", "entrada_teste")
    monkeypatch.setenv("LOG_FILE", "saida/teste.log")
    settings = Settings.from_env(tmp_path)
    assert settings.input_dir == tmp_path / "entrada_teste"
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
