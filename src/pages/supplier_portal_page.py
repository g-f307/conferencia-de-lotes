"""Page Object do portal controlado de fornecedores."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


class SupplierPortalPageTimeoutError(RuntimeError):
    """O portal não respondeu dentro do limite configurado."""


class SupplierPortalAuthenticationError(RuntimeError):
    """O portal recusou as credenciais fornecidas ao bot."""


class SupplierPortalDataError(RuntimeError):
    """O portal apresentou um pedido incompleto ou inválido."""


class SupplierPortalPage:
    """Encapsula autenticação, coleta semântica e evidência do portal."""

    LOGIN_HEADING = "Portal de fornecedores"
    ORDERS_HEADING = "Pedidos de fornecedores"
    TABLE_NAME = "Pedidos de fornecedores"
    AUTH_STATUS_NAME = "Resultado da autenticação"
    ORDER_FIELDS = (
        "pedido_id",
        "lote_id",
        "fornecedor",
        "produto",
        "quantidade_solicitada",
        "status_pedido",
        "data_prevista",
    )

    def __init__(self, page: Any, timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero")
        self.page = page
        self.timeout_seconds = timeout_seconds
        self.timeout_ms = timeout_seconds * 1_000

    def autenticar(self, usuario: str, senha: str) -> None:
        """Autentica sem registrar ou devolver os valores sigilosos."""
        if not usuario.strip() or not senha:
            raise SupplierPortalAuthenticationError(
                "Credenciais do portal não foram informadas"
            )
        try:
            self.page.get_by_role(
                "heading", name=self.LOGIN_HEADING, exact=True
            ).wait_for(state="visible", timeout=self.timeout_ms)
            self.page.get_by_label("Usuário", exact=True).fill(
                usuario.strip(), timeout=self.timeout_ms
            )
            self.page.get_by_label("Senha", exact=True).fill(
                senha, timeout=self.timeout_ms
            )
            self.page.get_by_role("button", name="Entrar", exact=True).click(
                timeout=self.timeout_ms
            )
            orders_heading = self.page.get_by_role(
                "heading", name=self.ORDERS_HEADING, exact=True
            )
            auth_error = self.page.locator('[data-auth-error="true"]')
            orders_heading.or_(auth_error).wait_for(
                state="visible", timeout=self.timeout_ms
            )
        except PlaywrightTimeoutError as exc:
            raise SupplierPortalPageTimeoutError(
                "Autenticação não terminou no tempo configurado"
            ) from exc

        error_status = self.page.locator('[data-auth-error="true"]')
        if error_status.count() and error_status.is_visible():
            raise SupplierPortalAuthenticationError(
                "O portal recusou as credenciais configuradas"
            )

    def coletar_pedidos(self) -> list[dict[str, object]]:
        """Lê pedidos da tabela visível sem acessar estado interno da aplicação."""
        try:
            self.page.get_by_role(
                "heading", name=self.ORDERS_HEADING, exact=True
            ).wait_for(state="visible", timeout=self.timeout_ms)
            table = self.page.get_by_role("table", name=self.TABLE_NAME)
            table.wait_for(state="visible", timeout=self.timeout_ms)
            rows = table.locator("tbody tr")
            rows.first.wait_for(state="visible", timeout=self.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise SupplierPortalPageTimeoutError(
                "Tabela de pedidos não ficou disponível no tempo configurado"
            ) from exc

        orders: list[dict[str, object]] = []
        for row_index in range(rows.count()):
            cells = rows.nth(row_index).get_by_role("cell").all_inner_texts()
            if len(cells) != len(self.ORDER_FIELDS):
                raise SupplierPortalDataError(
                    f"Pedido da linha {row_index + 1} possui estrutura inválida"
                )
            order = dict(zip(self.ORDER_FIELDS, (value.strip() for value in cells)))
            orders.append(self._validate_order(order, row_index + 1))
        return orders

    def capturar_evidencia(self, destination: Path) -> Path:
        """Persiste uma captura sanitizada da listagem exibida."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(destination), full_page=True)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise SupplierPortalDataError(
                "A evidência da coleta não foi persistida"
            )
        return destination

    @classmethod
    def _validate_order(
        cls, order: dict[str, str], row_number: int
    ) -> dict[str, object]:
        missing = [field for field in cls.ORDER_FIELDS if not order[field]]
        if missing:
            raise SupplierPortalDataError(
                f"Pedido da linha {row_number} possui campo obrigatório vazio: "
                + ", ".join(missing)
            )
        try:
            quantity = int(order["quantidade_solicitada"])
        except ValueError as exc:
            raise SupplierPortalDataError(
                f"Pedido da linha {row_number} possui quantidade inválida"
            ) from exc
        if quantity <= 0:
            raise SupplierPortalDataError(
                f"Pedido da linha {row_number} possui quantidade não positiva"
            )
        return {**order, "quantidade_solicitada": quantity}
