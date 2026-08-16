import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.pages.login_page import LoginPage, LoginPageTimeoutError


pytestmark = pytest.mark.unit


class FakeLocator:
    def __init__(self, *, timeout=False):
        self.actions = []
        self.timeout = timeout

    def fill(self, value, timeout=None):
        self.actions.append(("fill", value, timeout))

    def click(self, timeout=None):
        self.actions.append(("click", timeout))

    def wait_for(self, state=None, timeout=None):
        self.actions.append(("wait_for", state, timeout))
        if self.timeout:
            raise PlaywrightTimeoutError("timeout de teste")


class FakePage:
    def __init__(self, *, form_timeout=False):
        self.usuario = FakeLocator()
        self.senha = FakeLocator()
        self.botao = FakeLocator()
        self.formulario = FakeLocator(timeout=form_timeout)
        self.calls = []

    def get_by_label(self, name, exact=False):
        self.calls.append(("label", name, exact))
        return {
            LoginPage.ROTULO_USUARIO: self.usuario,
            LoginPage.ROTULO_SENHA: self.senha,
        }[name]

    def get_by_role(self, role, name=None, exact=False):
        self.calls.append(("role", role, name, exact))
        if role == "button":
            return self.botao
        return self.formulario


def test_login_page_centraliza_locators_semanticos():
    assert LoginPage.ROTULO_USUARIO == "Usuário"
    assert LoginPage.ROTULO_SENHA == "Senha"
    assert LoginPage.NOME_BOTAO_LOGIN == "Entrar"
    assert LoginPage.TITULO_FORMULARIO == "Processar novo lote"


def test_fazer_login_preenche_campos_e_valida_formulario():
    page = FakePage()

    LoginPage(page).fazer_login(" usuario.teste ", "senha-efemera")

    assert page.usuario.actions[0][:2] == ("fill", "usuario.teste")
    assert page.senha.actions[0][:2] == ("fill", "senha-efemera")
    assert page.botao.actions[0][0] == "click"
    assert page.formulario.actions[0][0] == "wait_for"
    assert ("label", "Usuário", True) in page.calls
    assert ("role", "button", "Entrar", True) in page.calls


@pytest.mark.parametrize(
    ("usuario", "senha"),
    [
        ("", "senha-efemera"),
        ("   ", "senha-efemera"),
        ("usuario.teste", ""),
    ],
)
def test_fazer_login_exige_usuario_e_senha(usuario, senha):
    page = FakePage()

    with pytest.raises(ValueError, match="Usuário e senha devem ser informados"):
        LoginPage(page).fazer_login(usuario, senha)

    assert page.usuario.actions == []
    assert page.senha.actions == []


def test_fazer_login_trata_timeout_sem_expor_credenciais():
    page = FakePage(form_timeout=True)
    usuario = "usuario-confidencial"
    senha = "senha-confidencial"

    with pytest.raises(LoginPageTimeoutError) as captured:
        LoginPage(page).fazer_login(usuario, senha)

    error_message = str(captured.value)
    assert usuario not in error_message
    assert senha not in error_message
    assert "tempo configurado" in error_message


def test_login_page_rejeita_timeout_invalido():
    with pytest.raises(ValueError, match="timeout_seconds"):
        LoginPage(FakePage(), timeout_seconds=0)
