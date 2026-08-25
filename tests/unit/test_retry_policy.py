from __future__ import annotations

import pytest

from src.retry_policy import LinearRetryPolicy, RetryExhaustedError

pytestmark = pytest.mark.unit


class AdvancingClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def test_retry_linear_aplica_intervalos_base_vezes_tentativa():
    clock = AdvancingClock()
    timeouts = []
    calls = 0
    policy = LinearRetryPolicy(
        max_attempts=3,
        base_interval_seconds=2,
        timeout_seconds=7,
        sleep=clock.sleep,
        clock=clock.monotonic,
    )

    def operation(timeout_seconds):
        nonlocal calls
        calls += 1
        timeouts.append(timeout_seconds)
        if calls < 3:
            raise ConnectionError("base indisponível")
        return "ok"

    result = policy.execute(operation, retry_on=(ConnectionError,))

    assert result.value == "ok"
    assert result.attempts == 3
    assert result.elapsed_seconds == 6
    assert clock.sleeps == [2, 4]
    assert timeouts == [7, 7, 7]


def test_retry_esgotado_preserva_tentativas_erro_e_tempo():
    clock = AdvancingClock()
    policy = LinearRetryPolicy(
        max_attempts=3,
        base_interval_seconds=1,
        timeout_seconds=5,
        sleep=clock.sleep,
        clock=clock.monotonic,
    )

    with pytest.raises(RetryExhaustedError) as captured:
        policy.execute(
            lambda timeout: (_ for _ in ()).throw(TimeoutError("timeout")),
            retry_on=(TimeoutError,),
        )

    assert captured.value.attempts == 3
    assert isinstance(captured.value.last_error, TimeoutError)
    assert captured.value.elapsed_seconds == 3
    assert clock.sleeps == [1, 2]


def test_retry_nao_intercepta_falha_fora_do_contrato():
    clock = AdvancingClock()
    policy = LinearRetryPolicy(
        max_attempts=4,
        base_interval_seconds=1,
        timeout_seconds=5,
        sleep=clock.sleep,
        clock=clock.monotonic,
    )

    with pytest.raises(ValueError, match="dado inválido"):
        policy.execute(
            lambda timeout: (_ for _ in ()).throw(ValueError("dado inválido")),
            retry_on=(ConnectionError,),
        )

    assert clock.sleeps == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_attempts", 0),
        ("base_interval_seconds", 0),
        ("timeout_seconds", float("nan")),
    ],
)
def test_retry_rejeita_configuracao_invalida(field, value):
    values = {
        "max_attempts": 3,
        "base_interval_seconds": 1,
        "timeout_seconds": 5,
        field: value,
    }

    with pytest.raises(ValueError, match=field):
        LinearRetryPolicy(**values)


def test_retry_exige_lista_de_excecoes():
    policy = LinearRetryPolicy(3, 1, 5)

    with pytest.raises(ValueError, match="retry_on"):
        policy.execute(lambda timeout: True, retry_on=())


@pytest.mark.parametrize("failed_attempt", [0, 3, 1.5, True])
def test_retry_rejeita_espera_fora_do_orcamento(failed_attempt):
    policy = LinearRetryPolicy(3, 1, 5, sleep=lambda seconds: None)

    with pytest.raises(ValueError, match="failed_attempt"):
        policy.wait_before_retry(failed_attempt)
