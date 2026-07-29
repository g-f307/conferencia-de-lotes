"""Page Object da autenticação do ambiente web controlado."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


class LoginPageTimeoutError(RuntimeError):
    """A tela de login não respondeu dentro do tempo configurado."""


class LoginPage:
    """Encapsula locators semânticos, waits e ações da autenticação."""

    ROTULO_USUARIO = "Usuário"
    ROTULO_SENHA = "Senha"
    NOME_BOTAO_LOGIN = "Entrar"
    TITULO_FORMULARIO = "Processar novo lote"

    def __init__(self, page: Any, timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero")

        self.page = page
        self.timeout_seconds = timeout_seconds
        self.timeout_ms = timeout_seconds * 1_000

    def fazer_login(self, usuario: str, senha: str) -> None:
        """Autentica e espera o formulário de lotes ficar disponível."""
        normalized_user = usuario.strip()
        if not normalized_user or not senha:
            raise ValueError("Usuário e senha devem ser informados")

        try:
            self.page.get_by_label(
                self.ROTULO_USUARIO,
                exact=True,
            ).fill(normalized_user, timeout=self.timeout_ms)
            self.page.get_by_label(
                self.ROTULO_SENHA,
                exact=True,
            ).fill(senha, timeout=self.timeout_ms)
            self.page.get_by_role(
                "button",
                name=self.NOME_BOTAO_LOGIN,
                exact=True,
            ).click(timeout=self.timeout_ms)
            self.page.get_by_role(
                "heading",
                name=self.TITULO_FORMULARIO,
                exact=True,
            ).wait_for(state="visible", timeout=self.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise LoginPageTimeoutError(
                "Não foi possível concluir o login no tempo configurado"
            ) from exc
