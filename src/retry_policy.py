"""Política de retry linear para dependências de infraestrutura."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


class RetryExhaustedError(RuntimeError):
    """Sinaliza que todas as tentativas de infraestrutura falharam."""

    def __init__(
        self,
        attempts: int,
        last_error: Exception,
        elapsed_seconds: float,
    ) -> None:
        message = str(last_error).strip() or f"{type(last_error).__name__} sem mensagem"
        super().__init__(
            f"Retry esgotado após {attempts} tentativa(s): {message}"
        )
        self.attempts = attempts
        self.last_error = last_error
        self.elapsed_seconds = elapsed_seconds


@dataclass(frozen=True)
class RetryResult(Generic[T]):
    value: T
    attempts: int
    elapsed_seconds: float


@dataclass(frozen=True)
class LinearRetryPolicy:
    max_attempts: int
    base_interval_seconds: float
    timeout_seconds: float
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or self.max_attempts < 1:
            raise ValueError("max_attempts deve ser um inteiro maior que zero")
        for field_name, value in (
            ("base_interval_seconds", self.base_interval_seconds),
            ("timeout_seconds", self.timeout_seconds),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} deve ser maior que zero")

    def execute(
        self,
        operation: Callable[[float], T],
        *,
        retry_on: tuple[type[Exception], ...],
    ) -> RetryResult[T]:
        """Executa a operação e espera base × tentativa entre falhas."""
        if not retry_on:
            raise ValueError("retry_on deve informar ao menos uma exceção")

        started_at = self.clock()
        for attempt in range(1, self.max_attempts + 1):
            try:
                value = operation(self.timeout_seconds)
            except retry_on as exc:
                if attempt == self.max_attempts:
                    raise RetryExhaustedError(
                        attempt,
                        exc,
                        self._elapsed(started_at),
                    ) from exc
                self.wait_before_retry(attempt)
            else:
                return RetryResult(
                    value=value,
                    attempts=attempt,
                    elapsed_seconds=self._elapsed(started_at),
                )

        raise AssertionError("Loop de retry terminou sem resultado")

    def wait_before_retry(self, failed_attempt: int) -> None:
        """Espera o intervalo linear correspondente à tentativa que falhou."""
        if (
            isinstance(failed_attempt, bool)
            or not isinstance(failed_attempt, int)
            or failed_attempt < 1
            or failed_attempt >= self.max_attempts
        ):
            raise ValueError(
                "failed_attempt deve identificar uma tentativa anterior ao limite"
            )
        self.sleep(self.base_interval_seconds * failed_attempt)

    def _elapsed(self, started_at: float) -> float:
        return max(0.0, self.clock() - started_at)
