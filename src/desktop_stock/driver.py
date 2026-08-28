"""Fronteira injetável para interação visual com o desktop."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Protocol, runtime_checkable


class DesktopAutomationError(RuntimeError):
    """Erro transitório ou terminal observado na interface desktop."""


@runtime_checkable
class DesktopDriver(Protocol):
    """Contrato mínimo usado pelo coletor, substituível em testes."""

    def wait_until_ready(self, timeout_seconds: float) -> None: ...

    def search(self, query: str, timeout_seconds: float) -> None: ...

    def read_visible_records(self, timeout_seconds: float) -> str: ...

    def capture_evidence(self, destination: Path) -> Path: ...

    def close(self) -> None: ...


class PyAutoGuiDesktopDriver:
    """Driver real que reconhece marcadores na tela e opera mouse/teclado.

    O driver não importa o simulador nem lê sua massa interna. A única entrada
    de negócio é o texto visível copiado da área de resultados após cliques e
    atalhos de teclado.
    """

    READY_COLOR = (30, 136, 229)
    SEARCH_COLOR = (194, 24, 91)
    RESULTS_COLOR = (0, 137, 123)
    SIMULATOR_WINDOW_TITLE = "Sistema Legado de Estoque - Capstone"

    def __init__(self, *, poll_interval_seconds: float = 0.1) -> None:
        if sys.platform != "win32":
            raise DesktopAutomationError(
                "o driver visual real requer uma sessão gráfica do Windows"
            )
        try:
            import pyautogui
        except ImportError as exc:
            raise DesktopAutomationError(
                "pyautogui não está instalado no Runner desktop"
            ) from exc
        self._gui = pyautogui
        self._poll_interval_seconds = poll_interval_seconds

    def wait_until_ready(self, timeout_seconds: float) -> None:
        self._wait_for_color(self.READY_COLOR, timeout_seconds)

    def search(self, query: str, timeout_seconds: float) -> None:
        marker_x, marker_y = self._wait_for_color(
            self.SEARCH_COLOR,
            timeout_seconds,
        )
        self._gui.click(marker_x + 190, marker_y)
        self._gui.hotkey("ctrl", "a")
        self._gui.write(query, interval=0.03)
        self._gui.press("enter")
        self._wait_for_color(self.RESULTS_COLOR, timeout_seconds)

    def read_visible_records(self, timeout_seconds: float) -> str:
        marker_x, marker_y = self._wait_for_color(
            self.RESULTS_COLOR,
            timeout_seconds,
        )
        self._gui.click(marker_x + 320, marker_y + 75)
        self._gui.hotkey("ctrl", "a")
        self._clear_windows_clipboard()
        self._gui.hotkey("ctrl", "c")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            content = self._read_windows_clipboard()
            if content.strip():
                return content
            time.sleep(self._poll_interval_seconds)
        raise DesktopAutomationError("timeout ao copiar os registros visíveis")

    def capture_evidence(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._gui.screenshot(region=self._simulator_window_region()).save(
                destination
            )
        except (OSError, self._gui.PyAutoGUIException) as exc:
            raise DesktopAutomationError(
                "não foi possível capturar a evidência visual"
            ) from exc
        return destination

    def _simulator_window_region(self) -> tuple[int, int, int, int]:
        """Restringe a evidência à janela controlada, sem expor o desktop."""
        user32 = ctypes.windll.user32
        window = user32.GetForegroundWindow()
        if not window:
            raise DesktopAutomationError("nenhuma janela ativa para evidência")

        title_length = user32.GetWindowTextLengthW(window)
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(window, title_buffer, title_length + 1)
        if title_buffer.value != self.SIMULATOR_WINDOW_TITLE:
            raise DesktopAutomationError(
                "a janela ativa não é o simulador de estoque controlado"
            )

        rect = wintypes.RECT()
        if not user32.GetWindowRect(window, ctypes.byref(rect)):
            raise DesktopAutomationError(
                "não foi possível obter a área da janela do simulador"
            )
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise DesktopAutomationError("área da janela do simulador é inválida")
        return rect.left, rect.top, width, height

    def close(self) -> None:
        """Libera teclas preventivamente sem encerrar o sistema consultado."""
        try:
            for key in ("ctrl", "shift", "alt"):
                self._gui.keyUp(key)
        except self._gui.PyAutoGUIException as exc:
            raise DesktopAutomationError(
                "não foi possível liberar as teclas do driver desktop"
            ) from exc

    def _wait_for_color(
        self,
        target: tuple[int, int, int],
        timeout_seconds: float,
    ) -> tuple[int, int]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            screenshot = self._gui.screenshot()
            location = self._find_color(screenshot, target)
            if location is not None:
                return location
            time.sleep(self._poll_interval_seconds)
        raise DesktopAutomationError(
            f"marcador visual {target} não encontrado dentro do timeout"
        )

    @staticmethod
    def _find_color(
        screenshot: object,
        target: tuple[int, int, int],
        *,
        tolerance: int = 5,
    ) -> tuple[int, int] | None:
        width, height = screenshot.size  # type: ignore[attr-defined]
        pixels = screenshot.load()  # type: ignore[attr-defined]
        for y in range(0, height, 3):
            for x in range(0, width, 3):
                pixel = pixels[x, y]
                matches = all(
                    abs(int(pixel[index]) - target[index]) <= tolerance
                    for index in range(3)
                )
                if matches:
                    return x + 6, y + 6
        return None

    @staticmethod
    def _clear_windows_clipboard() -> None:
        user32 = ctypes.windll.user32
        if not user32.OpenClipboard(None):
            return
        try:
            user32.EmptyClipboard()
        finally:
            user32.CloseClipboard()

    @staticmethod
    def _read_windows_clipboard() -> str:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetClipboardData.restype = ctypes.c_void_p
        user32.GetClipboardData.argtypes = [ctypes.c_uint]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not handle:
                return ""
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return ""
            try:
                return ctypes.wstring_at(pointer)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
