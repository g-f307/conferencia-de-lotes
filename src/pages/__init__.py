"""Page Objects usados pela automação web."""

from src.pages.form_page import (
    FormPage,
    FormPageResultError,
    FormPageTimeoutError,
)
from src.pages.login_page import LoginPage, LoginPageTimeoutError
from src.pages.supplier_portal_page import (
    SupplierPortalAuthenticationError,
    SupplierPortalDataError,
    SupplierPortalPage,
    SupplierPortalPageTimeoutError,
)

__all__ = [
    "FormPage",
    "FormPageResultError",
    "FormPageTimeoutError",
    "LoginPage",
    "LoginPageTimeoutError",
    "SupplierPortalAuthenticationError",
    "SupplierPortalDataError",
    "SupplierPortalPage",
    "SupplierPortalPageTimeoutError",
]
