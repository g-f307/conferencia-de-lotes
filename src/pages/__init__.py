"""Page Objects usados pela automação web."""

from src.pages.form_page import (
    FormPage,
    FormPageResultError,
    FormPageTimeoutError,
)
from src.pages.login_page import LoginPage, LoginPageTimeoutError

__all__ = [
    "FormPage",
    "FormPageResultError",
    "FormPageTimeoutError",
    "LoginPage",
    "LoginPageTimeoutError",
]
