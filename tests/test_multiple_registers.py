import json

from src.bot import DATAPOOL_LOG_LABEL, LOGGER as BOT_LOGGER
from src.config import Settings
from src.logging_config import LOGGER_NAME, configure_logging
from src.vault_client import LOGGER as VAULT_LOGGER


def configured_logger(tmp_path, monkeypatch, **environment):
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    settings = Settings.from_env(tmp_path)
    return configure_logging(tmp_path / "execucao.log", settings)


def test_log_contem_multiplos_registros(tmp_path):
    log_file = tmp_path / "execucao.log"

    logger = configure_logging(log_file)

    logger.info("Primeiro")
    logger.info("Segundo")
    logger.error("Terceiro")

    linhas = log_file.read_text(encoding="utf-8").splitlines()

    assert len(linhas) == 3

    for linha in linhas:
        json.loads(linha)

def test_log_possui_campos_obrigatorios(tmp_path, monkeypatch):
    log_file = tmp_path / "execucao.log"
    logger = configured_logger(
        tmp_path,
        monkeypatch,
        BOT_ID="auditor-lotes",
        EXECUTION_ID="exec-123",
    )

    logger.info(
        "Mensagem",
        extra={
            "evento": "TESTE",
            "formulario": "Login",
            "status": "SUCCESS",
        },
    )

    registro = json.loads(
        log_file.read_text(encoding="utf-8").splitlines()[0]
    )

    assert "timestamp" in registro
    assert "level" in registro
    assert registro["bot_id"] == "auditor-lotes"
    assert registro["execution_id"] == "exec-123"
    assert "evento" in registro
    assert "aplicacao" in registro
    assert "ambiente" in registro
    assert "usuario" in registro
    assert "detalhes" in registro

    assert "formulario" in registro["detalhes"]
    assert "status" in registro["detalhes"]
    assert "mensagem" in registro["detalhes"]

def test_log_usa_valores_padrao(tmp_path, monkeypatch):
    log_file = tmp_path / "execucao.log"
    monkeypatch.delenv("BOT_ID", raising=False)
    monkeypatch.delenv("EXECUTION_ID", raising=False)
    monkeypatch.setattr("sys.argv", ["bot.py"])
    logger = configure_logging(log_file)

    logger.info("Teste")

    registro = json.loads(
        log_file.read_text().splitlines()[0]
    )

    assert registro["evento"] == "LOG"
    assert registro["usuario"] == "sistema"
    assert registro["bot_id"] == "bot-conferencia-de-lotes-v2"
    assert registro["execution_id"] == "execucao-local"

    assert registro["detalhes"]["formulario"] is None
    assert registro["detalhes"]["status"] is None

def test_log_vai_para_arquivo_e_console(tmp_path, capsys):
    log_file = tmp_path / "execucao.log"

    logger = configure_logging(log_file)

    logger.info("Teste console")

    saida = capsys.readouterr()

    assert "Teste console" in saida.out

    texto = log_file.read_text()

    assert "Teste console" in texto

def test_log_nao_expoe_dados_sensiveis(tmp_path, monkeypatch):
    log_file = tmp_path / "execucao.log"
    senha = "SenhaSuperSecreta123"
    token = "TokenSuperSecreto456"
    maestro_key = "ChaveMaestro789"
    monkeypatch.setenv("MAESTRO_KEY", maestro_key)
    logger = configure_logging(log_file)

    logger.info(
        "Login: senha=%s token=%s chave=%s",
        senha,
        token,
        maestro_key,
    )

    texto = log_file.read_text()

    assert senha not in texto
    assert token not in texto
    assert maestro_key not in texto
    assert texto.count("[REDACTED]") == 3

def test_log_preserva_excecao(tmp_path):
    log_file = tmp_path / "execucao.log"

    logger = configure_logging(log_file)

    try:
        raise RuntimeError("Erro de teste")
    except RuntimeError:
        logger.exception("Falha")

    registro = json.loads(
        log_file.read_text().splitlines()[0]
    )

    assert "Erro de teste" in registro["detalhes"]["exception"]
    assert registro["detalhes"]["exception_type"] == "RuntimeError"
    assert registro["detalhes"]["exception_message"] == "Erro de teste"

def test_log_identifica_ambiente_runner(tmp_path, monkeypatch):
    log_file = tmp_path / "execucao.log"
    monkeypatch.setattr(
        "sys.argv",
        ["bot.py", "https://maestro.botcity.dev", "123"],
    )

    logger = configure_logging(log_file)

    logger.info("Teste runner")

    registro = json.loads(
        log_file.read_text(encoding="utf-8").splitlines()[0]
    )

    assert registro["ambiente"] == "runner"


def test_modulos_usam_logger_estruturado_central(tmp_path):
    log_file = tmp_path / "execucao.log"
    configure_logging(log_file)

    BOT_LOGGER.info(
        "Leitura da fila",
        extra={
            "evento": "LEITURA_DATAPOOL",
            "formulario": DATAPOOL_LOG_LABEL,
            "status": "SUCCESS",
        },
    )
    VAULT_LOGGER.info(
        "Credencial recuperada",
        extra={
            "evento": "RECUPERACAO_CREDENCIAL",
            "formulario": "Vault",
            "status": "SUCCESS",
        },
    )

    registros = [
        json.loads(linha)
        for linha in log_file.read_text(encoding="utf-8").splitlines()
    ]

    assert BOT_LOGGER.name == LOGGER_NAME
    assert VAULT_LOGGER.name == LOGGER_NAME
    assert [registro["evento"] for registro in registros] == [
        "LEITURA_DATAPOOL",
        "RECUPERACAO_CREDENCIAL",
    ]
    assert registros[0]["detalhes"]["formulario"] == "FilaAuditoriaLotes2"
