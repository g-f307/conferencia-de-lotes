"""Page Object da autenticação do ambiente web controlado."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class LoginPageTimeoutError(RuntimeError):
    """A tela de login não respondeu dentro do tempo configurado."""


class LoginPage:
    """Encapsula locators, waits e ações da autenticação web."""

    CAMPO_USUARIO = (By.ID, "usuario")
    CAMPO_SENHA = (By.ID, "senha")
    BOTAO_LOGIN = (By.ID, "botao-login")
    FORMULARIO_LOTE = (By.ID, "lote-form")

    def __init__(
        self,
        driver: Any,
        timeout_seconds: float = 15.0,
        *,
        wait_factory: Callable[[Any, float], Any] = WebDriverWait,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero")

        self.driver = driver
        self.timeout_seconds = timeout_seconds
        self._wait = wait_factory(driver, timeout_seconds)

    def fazer_login(self, usuario: str, senha: str) -> None:
        """Preenche o login e aguarda a abertura do formulário de lotes."""
        normalized_user = usuario.strip()
        if not normalized_user or not senha:
            raise ValueError("Usuário e senha devem ser informados")

        try:
            user_input = self._wait.until(
                EC.visibility_of_element_located(self.CAMPO_USUARIO)
            )
            password_input = self._wait.until(
                EC.visibility_of_element_located(self.CAMPO_SENHA)
            )
            login_button = self._wait.until(
                EC.element_to_be_clickable(self.BOTAO_LOGIN)
            )

            user_input.clear()
            user_input.send_keys(normalized_user)
            password_input.clear()
            password_input.send_keys(senha)
            login_button.click()

            self._wait.until(
                EC.visibility_of_element_located(self.FORMULARIO_LOTE)
            )
        except TimeoutException as exc:
            raise LoginPageTimeoutError(
                "Não foi possível concluir o login no tempo configurado"
            ) from exc
