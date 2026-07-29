"""Page Objects usados pela automação web."""

from src.pages.form_page import FormPage, FormPageTimeoutError
from src.pages.login_page import LoginPage, LoginPageTimeoutError

__all__ = [
    "FormPage",
    "FormPageTimeoutError",
    "LoginPage",
    "LoginPageTimeoutError",
]
