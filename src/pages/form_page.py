"""Page Object do formulário controlado de lotes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


class FormPageTimeoutError(RuntimeError):
    """O formulário de lotes não respondeu dentro do tempo configurado."""


class FormPageResultError(RuntimeError):
    """A interface retornou um resultado diferente do solicitado pelo fluxo."""


class FormPage:
    """Centraliza locators semânticos e ações, sem regras RN01–RN07."""

    ROTULO_NUMERO_LOTE = "Número do lote"
    ROTULO_PRODUTO = "Produto"
    ROTULO_MENSAGEM_RESULTADO = "Mensagem do resultado"
    NOME_BOTAO_PROCESSAR = "Processar lote"
    NOME_REGIAO_RESULTADO = "Resultado do processamento"

    RESULTADOS_VISUAIS: ClassVar[dict[str, str]] = {
        "APROVADO": "Aprovado",
        "REPROVADO": "Reprovado",
        "DIVERGENCIA": "Divergência",
        "REVISAO": "Revisão humana",
        "PENDENTE_REVISAO": "Revisão humana",
        "ERRO": "Erro técnico",
    }

    def __init__(self, page: Any, timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero")

        self.page = page
        self.timeout_seconds = timeout_seconds
        self.timeout_ms = timeout_seconds * 1_000

    def preencher_lote(self, dados_lote: Mapping[str, Any]) -> str:
        """Preenche o formulário e devolve a mensagem visual apresentada."""
        numero_lote = self._campo_para_exibicao(
            dados_lote,
            "numero_lote",
            aliases=("lote_id",),
            fallback="Lote sem identificação",
        )
        produto = self._campo_para_exibicao(
            dados_lote,
            "produto",
            fallback="Não informado",
        )
        resultado = self._campo_obrigatorio(dados_lote, "resultado_validacao")
        mensagem = self._campo_para_exibicao(
            dados_lote,
            "mensagem_resultado",
            fallback="Resultado processado pela automação.",
        )
        nome_resultado = self._nome_resultado(resultado, numero_lote)

        try:
            self.page.get_by_label(
                self.ROTULO_NUMERO_LOTE,
                exact=True,
            ).fill(numero_lote, timeout=self.timeout_ms)
            self.page.get_by_label(
                self.ROTULO_PRODUTO,
                exact=True,
            ).select_option(label=produto, timeout=self.timeout_ms)
            self.page.get_by_role(
                "radio",
                name=nome_resultado,
                exact=True,
            ).check(timeout=self.timeout_ms)
            self.page.get_by_label(
                self.ROTULO_MENSAGEM_RESULTADO,
                exact=True,
            ).fill(
                mensagem,
                timeout=self.timeout_ms,
            )
            self.page.get_by_role(
                "button",
                name=self.NOME_BOTAO_PROCESSAR,
                exact=True,
            ).click(timeout=self.timeout_ms)
            return self._aguardar_resultado()
        except PlaywrightTimeoutError as exc:
            raise FormPageTimeoutError(
                "Formulário não respondeu para o lote "
                f"{numero_lote} em até {self.timeout_seconds:g} segundos"
            ) from exc

    def validar_resultado(self, resultado_esperado: str) -> str:
        """Confirma que a apresentação corresponde à classificação recebida."""
        mensagem = self._aguardar_resultado()
        resultado = resultado_esperado.strip().upper()
        marcador = self.RESULTADOS_VISUAIS.get(resultado)
        if marcador is None:
            raise ValueError(f"Resultado visual desconhecido: {resultado_esperado!r}")

        estado = self.page.get_by_role(
            "status",
            name=self.NOME_REGIAO_RESULTADO,
        ).get_attribute("data-resultado")
        if str(estado or "").strip().upper() != resultado:
            raise FormPageResultError(
                "A interface não apresentou o resultado esperado para o item"
            )
        return mensagem

    def is_sucesso(self) -> bool:
        """Mantém a consulta legível usada pelos consumidores do Page Object."""
        estado = self.page.get_by_role(
            "status",
            name=self.NOME_REGIAO_RESULTADO,
        ).get_attribute("data-resultado")
        return str(estado or "").strip().upper() == "APROVADO"

    def capturar_evidencia(self, destino: Path) -> Path:
        """Captura a página após o resultado e confirma a persistência do PNG."""
        self._aguardar_resultado()
        destino.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(destino), full_page=True)
        if not destino.is_file() or destino.stat().st_size == 0:
            raise FormPageResultError(
                f"A evidência visual não foi persistida: {destino}"
            )
        return destino

    def _aguardar_resultado(self) -> str:
        try:
            region = self.page.get_by_role(
                "status",
                name=self.NOME_REGIAO_RESULTADO,
            )
            region.wait_for(state="visible", timeout=self.timeout_ms)
            return region.inner_text(timeout=self.timeout_ms).strip()
        except PlaywrightTimeoutError as exc:
            raise FormPageTimeoutError(
                "Mensagem de resultado não ficou visível em até "
                f"{self.timeout_seconds:g} segundos"
            ) from exc

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
        raise ValueError(f"Campo obrigatório ausente ou vazio: {nomes}")

    @classmethod
    def _campo_para_exibicao(
        cls,
        dados_lote: Mapping[str, Any],
        campo: str,
        *,
        aliases: tuple[str, ...] = (),
        fallback: str,
    ) -> str:
        try:
            return cls._campo_obrigatorio(dados_lote, campo, aliases=aliases)
        except ValueError:
            return fallback

    @classmethod
    def _nome_resultado(cls, resultado: str, numero_lote: str) -> str:
        normalized = resultado.strip().upper()
        try:
            return cls.RESULTADOS_VISUAIS[normalized]
        except KeyError as exc:
            raise ValueError(
                f"Resultado inválido para o lote {numero_lote}: {resultado!r}"
            ) from exc
