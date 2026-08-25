import logging
from typing import ClassVar

import pytest

from src.alerts import (
    Alerta,
    CanalEmail,
    Severidade,
    SistemaAlertas,
)

pytestmark = pytest.mark.unit


class CanalFake:
    def __init__(self, nome: str, *, falhar: bool = False, segredo: str = ""):
        self.nome = nome
        self.falhar = falhar
        self.segredo = segredo
        self.alertas = []

    def enviar(self, alerta):
        self.alertas.append(alerta)
        if self.falhar:
            raise RuntimeError(f"canal indisponivel {self.segredo}")


class SMTPFake:
    instances: ClassVar[list] = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls = False
        self.login_args = None
        self.messages = []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def starttls(self):
        self.tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.messages.append(message)


def alerta(severidade=Severidade.INFO):
    return Alerta(
        severidade=severidade,
        execution_id="exec-97",
        bot_id="bot-97",
        quantidade_afetada=2,
        motivo_predominante="timeout",
        estado_pipeline="PARTIALLY_COMPLETED",
    )


def sistema(telegram, email, local):
    return SistemaAlertas(
        telegram,
        email,
        local,
        logger=logging.getLogger("test.alertas"),
    )


def test_info_usa_telegram_como_canal_principal():
    telegram = CanalFake("telegram")
    email = CanalFake("email")
    local = CanalFake("log_local")

    result = sistema(telegram, email, local).notificar(alerta())

    assert result.entregues == ("telegram",)
    assert result.falhos == ()
    assert len(telegram.alertas) == 1
    assert email.alertas == []
    assert local.alertas == []


def test_erro_e_critico_usam_telegram_e_email():
    for severity in (Severidade.ERRO, Severidade.CRITICO):
        telegram = CanalFake("telegram")
        email = CanalFake("email")
        local = CanalFake("log_local")

        result = sistema(telegram, email, local).notificar(alerta(severity))

        assert result.entregues == ("telegram", "email")
        assert len(email.alertas) == 1
        assert local.alertas == []


def test_token_telegram_invalido_aciona_email_sem_interromper():
    telegram = CanalFake("telegram", falhar=True, segredo="token-invalido")
    email = CanalFake("email")
    local = CanalFake("log_local")

    result = sistema(telegram, email, local).notificar(alerta(Severidade.AVISO))

    assert result.entregues == ("email",)
    assert result.falhos == ("telegram",)
    assert len(email.alertas) == 1
    assert local.alertas == []


def test_falha_dos_canais_externos_usa_log_local():
    telegram = CanalFake("telegram", falhar=True)
    email = CanalFake("email", falhar=True)
    local = CanalFake("log_local")

    result = sistema(telegram, email, local).notificar(alerta())

    assert result.entregues == ("log_local",)
    assert result.falhos == ("telegram", "email")
    assert len(local.alertas) == 1


def test_falha_do_email_em_alerta_critico_e_registrada_localmente():
    telegram = CanalFake("telegram")
    email = CanalFake("email", falhar=True)
    local = CanalFake("log_local")

    result = sistema(telegram, email, local).notificar(alerta(Severidade.CRITICO))

    assert result.entregues == ("telegram", "log_local")
    assert result.falhos == ("email",)


def test_aviso_sem_ml_exige_divergencias_e_cem_por_cento_fallback():
    telegram = CanalFake("telegram")
    alerts = sistema(telegram, CanalFake("email"), CanalFake("log_local"))

    assert (
        alerts.avisar_pipeline_sem_ml(
            [],
            execution_id="exec-97",
            bot_id="bot-97",
            estado_pipeline="SUCCESS",
        )
        is None
    )
    assert (
        alerts.avisar_pipeline_sem_ml(
            [
                {"origem_decisao": "fallback", "motivo_fallback": "timeout"},
                {"origem_decisao": "ml", "motivo_fallback": None},
            ],
            execution_id="exec-97",
            bot_id="bot-97",
            estado_pipeline="SUCCESS",
        )
        is None
    )
    result = alerts.avisar_pipeline_sem_ml(
        [
            {"origem_decisao": "fallback", "motivo_fallback": "timeout"},
            {"origem_decisao": "fallback", "motivo_fallback": "timeout"},
            {
                "origem_decisao": "fallback",
                "motivo_fallback": "indisponibilidade",
            },
        ],
        execution_id="exec-97",
        bot_id="bot-97",
        estado_pipeline="PARTIALLY_COMPLETED",
    )

    assert result is not None
    sent = telegram.alertas[-1]
    assert sent.severidade is Severidade.AVISO
    assert sent.quantidade_afetada == 3
    assert sent.motivo_predominante == "timeout"
    assert sent.evento == "pipeline_operando_sem_ml"
    assert "evento=pipeline_operando_sem_ml" in sent.texto()
    assert "exec-97" in sent.texto()
    assert "bot-97" in sent.texto()


def test_excecao_de_canal_nao_expoe_segredos_no_log(caplog):
    caplog.set_level(logging.WARNING, logger="test.alertas")
    telegram = CanalFake("telegram", falhar=True, segredo="token-super-secreto")

    sistema(
        telegram,
        CanalFake("email"),
        CanalFake("log_local"),
    ).notificar(alerta())

    assert "token-super-secreto" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_canal_email_autentica_e_entrega_sem_expor_senha():
    SMTPFake.instances.clear()
    channel = CanalEmail(
        "smtp.example",
        587,
        "bot@example.com",
        ("operacao@example.com",),
        username="bot",
        password="senha-secreta",
        smtp_factory=SMTPFake,
    )

    channel.enviar(alerta(Severidade.ERRO))

    smtp = SMTPFake.instances[-1]
    assert smtp.tls is True
    assert smtp.login_args == ("bot", "senha-secreta")
    assert len(smtp.messages) == 1
    assert "senha-secreta" not in smtp.messages[0].as_string()
