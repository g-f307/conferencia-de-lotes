import json

from src.logging_config import configure_logging

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

def test_log_possui_campos_obrigatorios(tmp_path):
    log_file = tmp_path / "execucao.log"

    logger = configure_logging(log_file)

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
    assert "evento" in registro
    assert "aplicacao" in registro
    assert "ambiente" in registro
    assert "usuario" in registro
    assert "detalhes" in registro

    assert "formulario" in registro["detalhes"]
    assert "status" in registro["detalhes"]
    assert "mensagem" in registro["detalhes"]

def test_log_usa_valores_padrao(tmp_path):
    log_file = tmp_path / "execucao.log"

    logger = configure_logging(log_file)

    logger.info("Teste")

    registro = json.loads(
        log_file.read_text().splitlines()[0]
    )

    assert registro["evento"] == "LOG"
    assert registro["usuario"] == "sistema"

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

def test_log_nao_expoe_senha(tmp_path):
    log_file = tmp_path / "execucao.log"

    logger = configure_logging(log_file)

    senha = "SenhaSuperSecreta123"

    logger.info("Login realizado")

    texto = log_file.read_text()

    assert senha not in texto

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
