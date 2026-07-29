from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.pages.form_page import (
    FormPage,
    FormPageResultError,
    FormPageTimeoutError,
)


class FakeLocator:
    def __init__(self, *, text="", result="APROVADO", timeout=False):
        self.actions = []
        self.text = text
        self.result = result
        self.timeout = timeout

    def fill(self, value, timeout=None):
        self.actions.append(("fill", value, timeout))

    def select_option(self, label=None, timeout=None):
        self.actions.append(("select_option", label, timeout))

    def check(self, timeout=None):
        self.actions.append(("check", timeout))

    def click(self, timeout=None):
        self.actions.append(("click", timeout))

    def wait_for(self, state=None, timeout=None):
        self.actions.append(("wait_for", state, timeout))
        if self.timeout:
            raise PlaywrightTimeoutError("timeout de teste")

    def inner_text(self, timeout=None):
        return self.text

    def get_attribute(self, name):
        assert name == "data-resultado"
        return self.result


class FakePage:
    def __init__(
        self,
        *,
        result="APROVADO",
        message="Aprovado — lote L001",
        result_timeout=False,
    ):
        self.numero = FakeLocator()
        self.produto = FakeLocator()
        self.mensagem_configurada = FakeLocator()
        self.statuses = {
            name: FakeLocator()
            for name in FormPage.RESULTADOS_VISUAIS.values()
        }
        self.botao = FakeLocator()
        self.resultado = FakeLocator(
            text=message,
            result=result,
            timeout=result_timeout,
        )
        self.calls = []

    def get_by_label(self, name, exact=False):
        self.calls.append(("label", name, exact))
        return {
            FormPage.ROTULO_NUMERO_LOTE: self.numero,
            FormPage.ROTULO_PRODUTO: self.produto,
            FormPage.ROTULO_MENSAGEM_RESULTADO: self.mensagem_configurada,
        }[name]

    def get_by_role(self, role, name=None, exact=False):
        self.calls.append(("role", role, name, exact))
        if role == "radio":
            return self.statuses[name]
        if role == "button":
            return self.botao
        return self.resultado

    def screenshot(self, path, full_page=False):
        self.calls.append(("screenshot", path, full_page))
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\nfake")


def dados(**overrides):
    item = {
        "lote_id": "L001",
        "produto": "Monitor",
        "resultado_validacao": "APROVADO",
        "mensagem_resultado": "Lote aprovado",
    }
    item.update(overrides)
    return item


def test_form_page_centraliza_locators_semanticos():
    assert FormPage.ROTULO_NUMERO_LOTE == "Número do lote"
    assert FormPage.ROTULO_PRODUTO == "Produto"
    assert FormPage.NOME_BOTAO_PROCESSAR == "Processar lote"
    assert FormPage.RESULTADOS_VISUAIS["REPROVADO"] == "Reprovado"
    assert FormPage.RESULTADOS_VISUAIS["DIVERGENCIA"] == "Divergência"


def test_preencher_lote_usa_dados_do_item_e_resultado_recebido():
    page = FakePage()

    message = FormPage(page).preencher_lote(dados())

    assert page.numero.actions[0][:2] == ("fill", "L001")
    assert page.produto.actions[0][:2] == ("select_option", "Monitor")
    assert page.statuses["Aprovado"].actions[0][0] == "check"
    assert page.mensagem_configurada.actions[0][:2] == ("fill", "Lote aprovado")
    assert page.botao.actions[0][0] == "click"
    assert message == "Aprovado — lote L001"


def test_preencher_lote_usa_fallbacks_para_dados_invalidos():
    page = FakePage(result="DIVERGENCIA", message="Divergência")

    FormPage(page).preencher_lote(
        dados(
            lote_id="",
            produto="",
            resultado_validacao="DIVERGENCIA",
        )
    )

    assert page.numero.actions[0][1] == "Lote sem identificação"
    assert page.produto.actions[0][1] == "Não informado"
    assert page.statuses["Divergência"].actions[0][0] == "check"


def test_preencher_lote_preserva_reprovado_como_resultado_oficial():
    page = FakePage(result="REPROVADO", message="Reprovado — lote L001")

    message = FormPage(page).preencher_lote(
        dados(
            resultado_validacao="REPROVADO",
            mensagem_resultado="Lote reprovado: avaria",
        )
    )

    assert page.statuses["Reprovado"].actions[0][0] == "check"
    assert message == "Reprovado — lote L001"


def test_preencher_lote_rejeita_resultado_desconhecido():
    with pytest.raises(ValueError, match="Resultado inválido"):
        FormPage(FakePage()).preencher_lote(
            dados(resultado_validacao="DESCONHECIDO")
        )


def test_validar_resultado_confirma_classificacao_visual():
    page = FakePage(result="REVISAO", message="Revisão humana solicitada")

    message = FormPage(page).validar_resultado("REVISAO")

    assert message == "Revisão humana solicitada"


def test_validar_resultado_rejeita_classificacao_diferente():
    page = FakePage(result="DIVERGENCIA")

    with pytest.raises(FormPageResultError, match="resultado esperado"):
        FormPage(page).validar_resultado("APROVADO")


def test_resultado_trata_timeout():
    page = FakePage(result_timeout=True)

    with pytest.raises(FormPageTimeoutError, match="não ficou visível"):
        FormPage(page).validar_resultado("APROVADO")


def test_capturar_evidencia_confirma_png(tmp_path):
    destination = tmp_path / "artefatos" / "aprovado-L001.png"

    result = FormPage(FakePage()).capturar_evidencia(destination)

    assert result == destination
    assert destination.read_bytes().startswith(b"\x89PNG")


def test_is_sucesso_consulta_estado_da_interface():
    assert FormPage(FakePage(result="APROVADO")).is_sucesso() is True
    assert FormPage(FakePage(result="DIVERGENCIA")).is_sucesso() is False


def test_form_page_rejeita_timeout_invalido():
    with pytest.raises(ValueError, match="timeout_seconds"):
        FormPage(FakePage(), timeout_seconds=0)
