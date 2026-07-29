"""Page Object do formulario de lotes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
import unicodedata

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class FormPageTimeoutError(RuntimeError):
    """O formulário de lotes não respondeu dentro do tempo configurado."""


class FormPage:
    """Encapsula locators, waits e ações do formulário de lotes."""

    CAMPO_NUMERO_LOTE = (By.ID, "numero-lote")
    CAMPO_PRODUTO = (By.ID, "produto")
    STATUS_PENDENTE = (By.CSS_SELECTOR, '[data-testid="status-pendente"]')
    STATUS_PROCESSAMENTO = (By.CSS_SELECTOR, '[data-testid="status-processamento"]')
    STATUS_CONCLUIDO = (By.CSS_SELECTOR, '[data-testid="status-concluido"]')
    BOTAO_PROCESSAR = (By.ID, "botao-processar")
    MENSAGEM_RESULTADO = (By.ID, "mensagem")

    STATUS_OPCOES = {
        "Pendente": STATUS_PENDENTE,
        "Em Processamento": STATUS_PROCESSAMENTO,
        "Concluido": STATUS_CONCLUIDO,
        "Conclu\u00eddo": STATUS_CONCLUIDO,
    }

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

    def preencher_lote(self, dados_lote: Mapping[str, Any]) -> None:
        """Preenche número, produto, status e envia o formulário."""
        numero_lote = self._campo_obrigatorio(
            dados_lote,
            "numero_lote",
            aliases=("lote_id",),
        )
        produto = self._campo_obrigatorio(dados_lote, "produto")
        status = self._campo_obrigatorio(dados_lote, "status")
        status_locator = self._locator_status(status, numero_lote)

        numero_input = self._wait.until(
            EC.visibility_of_element_located(self.CAMPO_NUMERO_LOTE)
        )
        produto_input = self._wait.until(
            EC.visibility_of_element_located(self.CAMPO_PRODUTO)
        )
        status_option = self._wait.until(EC.element_to_be_clickable(status_locator))

        numero_input.clear()
        numero_input.send_keys(numero_lote)
        produto_input.clear()
        produto_input.send_keys(produto)
        status_option.click()

        try:
            button = self._wait.until(EC.element_to_be_clickable(self.BOTAO_PROCESSAR))
        except TimeoutException as exc:
            raise FormPageTimeoutError(
                "Botao de processamento nao ficou clicavel para o lote "
                f"{numero_lote} em ate {self.timeout_seconds:g} segundos "
                f"(locator={self.BOTAO_PROCESSAR!r})"
            ) from exc

        button.click()

    def is_sucesso(self) -> bool:
        """Aguarda a mensagem final e valida se ela confirma sucesso."""
        try:
            mensagem = self._wait.until(
                EC.visibility_of_element_located(self.MENSAGEM_RESULTADO)
            )
        except TimeoutException as exc:
            raise FormPageTimeoutError(
                "Mensagem de resultado nao ficou visivel em ate "
                f"{self.timeout_seconds:g} segundos "
                f"(locator={self.MENSAGEM_RESULTADO!r})"
            ) from exc

        texto = getattr(mensagem, "text", "") or ""
        return "sucesso" in texto.casefold()

    @classmethod
    def _campo_obrigatorio(
        cls,
        dados_lote: Mapping[str, Any],
        campo: str,
        *,
        aliases: tuple[str, ...] = (),
    ) -> str:
        for chave in (campo, *aliases):
            valor = dados_lote.get(chave)
            if valor is not None and str(valor).strip():
                return str(valor).strip()

        nomes = ", ".join((campo, *aliases))
        raise ValueError(f"Campo obrigatorio ausente ou vazio: {nomes}")

    @classmethod
    def _locator_status(cls, status: str, numero_lote: str) -> tuple[str, str]:
        normalized_status = cls._normalizar_status(status)
        for status_configurado, locator in cls.STATUS_OPCOES.items():
            if cls._normalizar_status(status_configurado) == normalized_status:
                return locator

        opcoes = ", ".join(cls.STATUS_OPCOES)
        raise ValueError(
            f"Status invalido para o lote {numero_lote}: {status!r}. "
            f"Opcoes validas: {opcoes}"
        )

    @staticmethod
    def _normalizar_status(status: str) -> str:
        without_accents = unicodedata.normalize("NFKD", status)
        ascii_status = without_accents.encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_status.casefold().split())
