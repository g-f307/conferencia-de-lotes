"""Notificacoes multicanal resilientes para eventos operacionais."""

from __future__ import annotations

import json
import logging
import smtplib
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from email.message import EmailMessage
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol
from urllib import request

if TYPE_CHECKING:
    from src.config import Settings


class Severidade(StrEnum):
    INFO = "INFO"
    AVISO = "AVISO"
    ERRO = "ERRO"
    CRITICO = "CRITICO"


@dataclass(frozen=True)
class Alerta:
    """Mensagem operacional sem dados livres ou credenciais."""

    severidade: Severidade
    execution_id: str
    bot_id: str
    quantidade_afetada: int
    motivo_predominante: str
    estado_pipeline: str
    evento: str = "alerta_operacional"

    def texto(self) -> str:
        return (
            f"[{self.severidade}] pipeline={self.estado_pipeline}; "
            f"execucao={self.execution_id}; bot={self.bot_id}; "
            f"quantidade_afetada={self.quantidade_afetada}; "
            f"motivo_predominante={self.motivo_predominante}; "
            f"evento={self.evento}"
        )


class CanalNotificacao(Protocol):
    nome: str

    def enviar(self, alerta: Alerta) -> None: ...


@dataclass(frozen=True)
class ResultadoEntrega:
    entregues: tuple[str, ...]
    falhos: tuple[str, ...]


class CanalTelegram:
    """Entrega alertas pela API HTTP do Telegram."""

    nome = "telegram"

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        timeout_seconds: float = 5.0,
        api_base_url: str = "https://api.telegram.org",
        opener: Callable[..., Any] = request.urlopen,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._timeout_seconds = timeout_seconds
        self._api_base_url = api_base_url.rstrip("/")
        self._opener = opener

    def enviar(self, alerta: Alerta) -> None:
        payload = json.dumps(
            {"chat_id": self._chat_id, "text": alerta.texto()},
            ensure_ascii=False,
        ).encode("utf-8")
        endpoint = f"{self._api_base_url}/bot{self._token}/sendMessage"
        http_request = request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._opener(http_request, timeout=self._timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if not 200 <= status < 300:
                raise RuntimeError("Telegram rejeitou a notificacao")


class CanalEmail:
    """Entrega alertas por SMTP com TLS opcional."""

    nome = "email"

    def __init__(
        self,
        host: str,
        port: int,
        remetente: str,
        destinatarios: Iterable[str],
        *,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        timeout_seconds: float = 5.0,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
    ) -> None:
        self._host = host
        self._port = port
        self._remetente = remetente
        self._destinatarios = tuple(destinatarios)
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._timeout_seconds = timeout_seconds
        self._smtp_factory = smtp_factory

    def enviar(self, alerta: Alerta) -> None:
        message = EmailMessage()
        message["Subject"] = f"[{alerta.severidade}] Auditoria de lotes"
        message["From"] = self._remetente
        message["To"] = ", ".join(self._destinatarios)
        message.set_content(alerta.texto())

        with self._smtp_factory(
            self._host,
            self._port,
            timeout=self._timeout_seconds,
        ) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)


class CanalLogLocal:
    """Ultimo recurso para preservar a perda dos canais externos."""

    nome = "log_local"

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def enviar(self, alerta: Alerta) -> None:
        self._logger.critical(
            "ALERTA LOCAL: perda de canal externo; %s",
            alerta.texto(),
            extra={
                "evento": "ALERTA_FALLBACK_LOCAL",
                "formulario": "SistemaAlertas",
                "status": alerta.severidade,
                "usuario": "sistema",
            },
        )


class SistemaAlertas:
    """Coordena Telegram, Email e log sem interromper o pipeline."""

    def __init__(
        self,
        telegram: CanalNotificacao,
        email: CanalNotificacao,
        log_local: CanalNotificacao,
        *,
        logger: logging.Logger,
    ) -> None:
        self._telegram = telegram
        self._email = email
        self._log_local = log_local
        self._logger = logger

    def notificar(self, alerta: Alerta) -> ResultadoEntrega:
        entregues: list[str] = []
        falhos: list[str] = []

        if self._tentar(self._telegram, alerta):
            entregues.append(self._telegram.nome)
        else:
            falhos.append(self._telegram.nome)

        enviar_email = (
            alerta.severidade in {Severidade.ERRO, Severidade.CRITICO}
            or not entregues
        )
        if enviar_email:
            if self._tentar(self._email, alerta):
                entregues.append(self._email.nome)
            else:
                falhos.append(self._email.nome)
                if self._tentar(self._log_local, alerta):
                    entregues.append(self._log_local.nome)
                else:
                    falhos.append(self._log_local.nome)

        return ResultadoEntrega(tuple(entregues), tuple(falhos))

    def avisar_pipeline_sem_ml(
        self,
        decisoes: Iterable[Mapping[str, Any]],
        *,
        execution_id: str,
        bot_id: str,
        estado_pipeline: str,
    ) -> ResultadoEntrega | None:
        """Avisa somente quando todas as divergencias dependeram de fallback."""
        divergencias = tuple(decisoes)
        if not divergencias or any(
            decisao.get("origem_decisao") != "fallback"
            for decisao in divergencias
        ):
            return None

        motivos = Counter(
            str(decisao.get("motivo_fallback") or "indisponibilidade")
            for decisao in divergencias
        )
        motivo_predominante = motivos.most_common(1)[0][0]
        return self.notificar(
            Alerta(
                severidade=Severidade.AVISO,
                execution_id=execution_id,
                bot_id=bot_id,
                quantidade_afetada=len(divergencias),
                motivo_predominante=motivo_predominante,
                estado_pipeline=estado_pipeline,
                evento="pipeline_operando_sem_ml",
            )
        )

    def _tentar(self, canal: CanalNotificacao, alerta: Alerta) -> bool:
        try:
            canal.enviar(alerta)
        except Exception as exc:  # noqa: BLE001 - notificacao nunca quebra o pipeline
            self._logger.warning(
                "Falha no canal %s (%s)",
                canal.nome,
                type(exc).__name__,
                extra={
                    "evento": "FALHA_CANAL_ALERTA",
                    "formulario": "SistemaAlertas",
                    "status": "FALLBACK",
                    "usuario": "sistema",
                },
            )
            return False
        return True


def construir_sistema_alertas(
    settings: Settings,
    logger: logging.Logger,
) -> SistemaAlertas | None:
    """Monta os canais somente quando a integracao esta habilitada."""
    if not settings.alerts_enabled:
        return None

    assert settings.smtp_port is not None
    assert settings.alerts_timeout_seconds is not None
    return SistemaAlertas(
        CanalTelegram(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            timeout_seconds=settings.alerts_timeout_seconds,
            api_base_url=settings.telegram_api_base_url,
        ),
        CanalEmail(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_from,
            settings.smtp_to,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            timeout_seconds=settings.alerts_timeout_seconds,
        ),
        CanalLogLocal(logger),
        logger=logger,
    )
