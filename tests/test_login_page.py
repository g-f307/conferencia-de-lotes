import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from src.pages.login_page import LoginPage, LoginPageTimeoutError


class FakeElement:
    def __init__(self, *, displayed=True, enabled=True):
        self.actions = []
        self.displayed = displayed
        self.enabled = enabled

    def clear(self):
        self.actions.append(("clear",))

    def send_keys(self, value):
        self.actions.append(("send_keys", value))

    def click(self):
        self.actions.append(("click",))

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled


class FakeDriver:
    def __init__(self, *, form_visible=True, button_enabled=True):
        self.elements = {
            (By.ID, "usuario"): FakeElement(),
            (By.ID, "senha"): FakeElement(),
            (By.ID, "botao-login"): FakeElement(enabled=button_enabled),
            (By.ID, "lote-form"): FakeElement(displayed=form_visible),
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


def build_login_page(driver, timeout=15):
    return LoginPage(
        driver,
        timeout_seconds=timeout,
        wait_factory=ImmediateWait,
    )


def test_login_page_centraliza_locators():
    assert LoginPage.CAMPO_USUARIO == (By.ID, "usuario")
    assert LoginPage.CAMPO_SENHA == (By.ID, "senha")
    assert LoginPage.BOTAO_LOGIN == (By.ID, "botao-login")
    assert LoginPage.FORMULARIO_LOTE == (By.ID, "lote-form")


def test_fazer_login_preenche_campos_e_clica_no_botao():
    driver = FakeDriver()

    build_login_page(driver).fazer_login(" usuario.teste ", "senha-efemera")

    assert driver.elements[LoginPage.CAMPO_USUARIO].actions == [
        ("clear",),
        ("send_keys", "usuario.teste"),
    ]
    assert driver.elements[LoginPage.CAMPO_SENHA].actions == [
        ("clear",),
        ("send_keys", "senha-efemera"),
    ]
    assert driver.elements[LoginPage.BOTAO_LOGIN].actions == [("click",)]


@pytest.mark.parametrize(
    ("usuario", "senha"),
    [
        ("", "senha-efemera"),
        ("   ", "senha-efemera"),
        ("usuario.teste", ""),
    ],
)
def test_fazer_login_exige_usuario_e_senha(usuario, senha):
    driver = FakeDriver()

    with pytest.raises(ValueError, match="Usuário e senha devem ser informados"):
        build_login_page(driver).fazer_login(usuario, senha)

    assert driver.elements[LoginPage.CAMPO_USUARIO].actions == []
    assert driver.elements[LoginPage.CAMPO_SENHA].actions == []


def test_fazer_login_trata_timeout_sem_expor_credenciais():
    driver = FakeDriver(form_visible=False)
    usuario = "usuario-confidencial"
    senha = "senha-confidencial"

    with pytest.raises(LoginPageTimeoutError) as captured:
        build_login_page(driver).fazer_login(usuario, senha)

    error_message = str(captured.value)
    assert usuario not in error_message
    assert senha not in error_message
    assert "tempo configurado" in error_message


def test_login_page_rejeita_timeout_invalido():
    with pytest.raises(ValueError, match="timeout_seconds"):
        build_login_page(FakeDriver(), timeout=0)
