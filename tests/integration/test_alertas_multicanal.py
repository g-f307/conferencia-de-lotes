import json
import logging
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import ClassVar

import pytest

from src.alerts import (
    Alerta,
    CanalEmail,
    CanalLogLocal,
    CanalTelegram,
    Severidade,
    SistemaAlertas,
)

pytestmark = pytest.mark.integration


class TelegramHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        self.__class__.requests.append((self.path, payload))
        status = 401 if "token-invalido" in self.path else 200
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, _format, *_args):
        return None


class SMTPRecorder:
    messages: ClassVar[list] = []

    def __init__(self, _host, _port, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def starttls(self):
        return None

    def login(self, _username, _password):
        return None

    def send_message(self, message):
        self.__class__.messages.append(message)


@contextmanager
def telegram_server():
    TelegramHandler.requests.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), TelegramHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def alerta(severidade):
    return Alerta(
        severidade=severidade,
        execution_id="exec-integracao",
        bot_id="bot-integracao",
        quantidade_afetada=4,
        motivo_predominante="timeout",
        estado_pipeline="PARTIALLY_COMPLETED",
    )


def build_system(api_url, token, caplog):
    SMTPRecorder.messages.clear()
    logger = logging.getLogger("test.alertas.integracao")
    caplog.set_level(logging.WARNING, logger=logger.name)
    return SistemaAlertas(
        CanalTelegram(token, "chat-operacao", api_base_url=api_url),
        CanalEmail(
            "smtp.local",
            587,
            "bot@example.com",
            ("operacao@example.com",),
            smtp_factory=SMTPRecorder,
        ),
        CanalLogLocal(logger),
        logger=logger,
    )


def test_alerta_de_erro_entrega_nos_dois_adaptadores(caplog):
    with telegram_server() as api_url:
        result = build_system(api_url, "token-valido", caplog).notificar(
            alerta(Severidade.ERRO)
        )

    assert result.entregues == ("telegram", "email")
    assert TelegramHandler.requests[0][0].endswith("/sendMessage")
    assert TelegramHandler.requests[0][1]["chat_id"] == "chat-operacao"
    assert "exec-integracao" in TelegramHandler.requests[0][1]["text"]
    assert len(SMTPRecorder.messages) == 1
    assert "bot-integracao" in SMTPRecorder.messages[0].get_content()


def test_token_telegram_invalido_faz_fallback_real_para_email(caplog):
    with telegram_server() as api_url:
        result = build_system(api_url, "token-invalido", caplog).notificar(
            alerta(Severidade.AVISO)
        )

    assert result.entregues == ("email",)
    assert result.falhos == ("telegram",)
    assert len(TelegramHandler.requests) == 1
    assert len(SMTPRecorder.messages) == 1
    assert "token-invalido" not in caplog.text
