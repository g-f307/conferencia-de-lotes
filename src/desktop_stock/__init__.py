"""Coleta visual do sistema legado simulado de estoque."""

from src.desktop_stock.collector import DesktopStockCollector
from src.desktop_stock.driver import (
    DesktopAutomationError,
    DesktopDriver,
    PyAutoGuiDesktopDriver,
)
from src.desktop_stock.models import DesktopCollectionContext, StockRecord

__all__ = [
    "DesktopAutomationError",
    "DesktopCollectionContext",
    "DesktopDriver",
    "DesktopStockCollector",
    "PyAutoGuiDesktopDriver",
    "StockRecord",
]
