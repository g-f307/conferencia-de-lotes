import pytest
from selenium.common.exceptions import InvalidElementStateException, TimeoutException
from selenium.webdriver.common.by import By

from src.pages.form_page import FormPage, FormPageTimeoutError


class FakeElement:
    def __init__(
        self,
        *,
        text="",
        displayed=True,
        enabled=True,
        tag_name="input",
        clear_allowed=True,
    ):
        self.actions = []
        self.text = text
        self.displayed = displayed
        self.enabled = enabled
        self.tag_name = tag_name
        self.clear_allowed = clear_allowed

    def clear(self):
        if not self.clear_allowed:
            raise InvalidElementStateException("clear indisponivel para este elemento")
        self.actions.append(("clear",))

    def send_keys(self, value):
        self.actions.append(("send_keys", value))

    def click(self):
        self.actions.append(("click",))

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled


class FakeOption(FakeElement):
    def __init__(self, text):
        super().__init__(text=text, tag_name="option")
        self.selected = False

    def click(self):
        self.selected = True
        self.actions.append(("click",))

    def is_selected(self):
        return self.selected

    def value_of_css_property(self, css_property):
        values = {
            "visibility": "visible",
            "display": "block",
            "opacity": "1",
        }
        return values[css_property]


class FakeSelectElement(FakeElement):
    def __init__(self, options):
        super().__init__(tag_name="select", clear_allowed=False)
        self.options = {option_text: FakeOption(option_text) for option_text in options}

    def get_dom_attribute(self, name):
        return None

    def find_elements(self, by, value):
        if by != By.XPATH:
            return []

        return [
            option
            for option_text, option in self.options.items()
            if f'"{option_text}"' in value or f"'{option_text}'" in value
        ]


class FakeDriver:
    def __init__(
        self,
        *,
        button_enabled=True,
        confirmation_visible=True,
        confirmation_text="Lote processado com sucesso.",
    ):
        self.elements = {
            FormPage.CAMPO_NUMERO_LOTE: FakeElement(),
            FormPage.CAMPO_PRODUTO: FakeSelectElement(["Monitor", "Scanner"]),
            FormPage.STATUS_PENDENTE: FakeElement(),
            FormPage.STATUS_PROCESSAMENTO: FakeElement(),
            FormPage.STATUS_CONCLUIDO: FakeElement(),
            FormPage.BOTAO_PROCESSAR: FakeElement(enabled=button_enabled),
            FormPage.MENSAGEM_RESULTADO: FakeElement(
                text=confirmation_text,
                displayed=confirmation_visible,
            ),
        }

    def find_element(self, by, value):
        return self.elements[(by, value)]


class ImmediateWait:
    def __init__(self, driver, timeout):
        self.driver = driver
        self.timeout = timeout

    def until(self, condition):
        result = condition(self.driver)
        if not result:
            raise TimeoutException("timeout de teste")
        return result


def build_form_page(driver, timeout=15):
    return FormPage(
        driver,
        timeout_seconds=timeout,
        wait_factory=ImmediateWait,
    )


def test_form_page_centraliza_locators():
    assert FormPage.CAMPO_NUMERO_LOTE == (By.ID, "numero-lote")
    assert FormPage.CAMPO_PRODUTO == (By.ID, "produto")
    assert FormPage.STATUS_PENDENTE == (
        By.XPATH,
        '//label[.//input[@data-testid="status-pendente"]]',
    )
    assert FormPage.STATUS_PROCESSAMENTO == (
        By.XPATH,
        '//label[.//input[@data-testid="status-processamento"]]',
    )
    assert FormPage.STATUS_CONCLUIDO == (
        By.XPATH,
        '//label[.//input[@data-testid="status-concluido"]]',
    )
    assert FormPage.BOTAO_PROCESSAR == (By.ID, "botao-processar")
    assert FormPage.MENSAGEM_RESULTADO == (By.ID, "mensagem")
    assert FormPage.STATUS_OPCOES["Pendente"] == FormPage.STATUS_PENDENTE


def test_preencher_lote_preenche_campos_status_e_envia_formulario():
    driver = FakeDriver()
    dados_lote = {
        "numero_lote": "LOTE-TESTE-001",
        "produto": "Scanner",
        "status": "Concluido",
    }

    build_form_page(driver).preencher_lote(dados_lote)

    assert driver.elements[FormPage.CAMPO_NUMERO_LOTE].actions == [
        ("clear",),
        ("send_keys", "LOTE-TESTE-001"),
    ]
    produto = driver.elements[FormPage.CAMPO_PRODUTO]
    assert produto.actions == []
    assert produto.options["Scanner"].actions == [("click",)]
    assert produto.options["Scanner"].is_selected() is True
    assert driver.elements[FormPage.STATUS_CONCLUIDO].actions == [("click",)]
    assert driver.elements[FormPage.BOTAO_PROCESSAR].actions == [("click",)]


def test_preencher_lote_aceita_lote_id_como_alias_do_numero():
    driver = FakeDriver()
    dados_lote = {
        "lote_id": "LOTE-ALIAS-001",
        "produto": "Monitor",
        "status": "Pendente",
    }

    build_form_page(driver).preencher_lote(dados_lote)

    assert driver.elements[FormPage.CAMPO_NUMERO_LOTE].actions == [
        ("clear",),
        ("send_keys", "LOTE-ALIAS-001"),
    ]


def test_preencher_lote_rejeita_status_desconhecido_com_contexto():
    driver = FakeDriver()
    dados_lote = {
        "numero_lote": "LOTE-TESTE-002",
        "produto": "Scanner",
        "status": "Cancelado",
    }

    with pytest.raises(ValueError, match="Status.*LOTE-TESTE-002.*Cancelado"):
        build_form_page(driver).preencher_lote(dados_lote)

    assert driver.elements[FormPage.BOTAO_PROCESSAR].actions == []


def test_preencher_lote_rejeita_produto_inexistente_com_contexto():
    driver = FakeDriver()

    with pytest.raises(ValueError, match="Produto.*LOTE-TESTE-004.*Inexistente"):
        build_form_page(driver).preencher_lote(
            {
                "numero_lote": "LOTE-TESTE-004",
                "produto": "Inexistente",
                "status": "Pendente",
            }
        )

    assert driver.elements[FormPage.BOTAO_PROCESSAR].actions == []


def test_preencher_lote_informa_timeout_do_botao_com_contexto():
    driver = FakeDriver(button_enabled=False)

    with pytest.raises(
        FormPageTimeoutError,
        match="Botao de processamento.*LOTE-TESTE-003.*15 segundos",
    ):
        build_form_page(driver).preencher_lote(
            {
                "numero_lote": "LOTE-TESTE-003",
                "produto": "Scanner",
                "status": "Pendente",
            }
        )


def test_preencher_lote_informa_timeout_do_status_com_contexto():
    driver = FakeDriver()
    driver.elements[FormPage.STATUS_CONCLUIDO].displayed = False

    with pytest.raises(
        FormPageTimeoutError,
        match="status Concluido.*LOTE-TESTE-005.*15 segundos.*status-concluido",
    ):
        build_form_page(driver).preencher_lote(
            {
                "numero_lote": "LOTE-TESTE-005",
                "produto": "Scanner",
                "status": "Concluido",
            }
        )

    assert driver.elements[FormPage.BOTAO_PROCESSAR].actions == []


def test_preencher_lote_informa_timeout_do_produto_com_contexto():
    driver = FakeDriver()
    driver.elements[FormPage.CAMPO_PRODUTO].displayed = False

    with pytest.raises(
        FormPageTimeoutError,
        match="produto.*LOTE-TESTE-006.*15 segundos.*produto",
    ):
        build_form_page(driver).preencher_lote(
            {
                "numero_lote": "LOTE-TESTE-006",
                "produto": "Scanner",
                "status": "Pendente",
            }
        )


def test_preencher_lote_informa_timeout_do_numero_com_contexto():
    driver = FakeDriver()
    driver.elements[FormPage.CAMPO_NUMERO_LOTE].displayed = False

    with pytest.raises(
        FormPageTimeoutError,
        match="numero do lote.*LOTE-TESTE-007.*15 segundos.*numero-lote",
    ):
        build_form_page(driver).preencher_lote(
            {
                "numero_lote": "LOTE-TESTE-007",
                "produto": "Scanner",
                "status": "Pendente",
            }
        )


def test_is_sucesso_aguarda_e_valida_mensagem_final():
    driver = FakeDriver(confirmation_text="Lote processado com sucesso.")

    assert build_form_page(driver).is_sucesso() is True


def test_is_sucesso_retorna_falso_para_mensagem_invalida():
    driver = FakeDriver(confirmation_text="Falha ao processar o lote.")

    assert build_form_page(driver).is_sucesso() is False


def test_is_sucesso_trata_confirmacao_ausente_ou_timeout():
    driver = FakeDriver(confirmation_visible=False)

    with pytest.raises(
        FormPageTimeoutError,
        match="Mensagem de resultado.*15 segundos.*mensagem",
    ):
        build_form_page(driver).is_sucesso()


def test_form_page_rejeita_timeout_invalido():
    with pytest.raises(ValueError, match="timeout_seconds"):
        build_form_page(FakeDriver(), timeout=0)
