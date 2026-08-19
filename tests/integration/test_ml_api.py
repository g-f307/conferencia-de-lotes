from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Coroutine, TypeVar

import httpx
import pytest

from api_ml import main as api_module
from api_ml.main import create_app, resolve_confidence, resolve_model_path


pytestmark = pytest.mark.integration
MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "classificador_lotes.pkl"
ResultT = TypeVar("ResultT")


def run_async(coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Isola o loop ASGI do loop de sessao usado pelo pytest-playwright."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result(timeout=15)


async def request(
    app: Any,
    method: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)


def test_predict_accepts_valid_payload():
    response = run_async(
        request(
            create_app(MODEL_PATH),
            "POST",
            "/predict",
            json={
                "lote_id": "L001",
                "status_raw": "Em análise",
                "turno": "Manhã",
                "tem_obs": True,
            },
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["classe"] == "valido_automatico"
    assert payload["probabilidade"] >= 0.85
    assert payload["nivel_confianca"] == "alta"
    assert payload["acao"] == "valido_automatico"


def test_predict_automatically_rejects_high_risk_ambiguous_case():
    response = run_async(
        request(
            create_app(MODEL_PATH),
            "POST",
            "/predict",
            json={
                "lote_id": "L004",
                "status_raw": "Especificação em revisão",
                "turno": "C",
                "tem_obs": False,
            },
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["classe"] == "recusar_automatico"
    assert payload["probabilidade"] >= 0.85
    assert payload["nivel_confianca"] == "alta"
    assert payload["acao"] == "recusar_automatico"


def test_predict_rejects_invalid_shift():
    response = run_async(
        request(
            create_app(MODEL_PATH),
            "POST",
            "/predict",
            json={
                "lote_id": "L002",
                "status_raw": "Pendente",
                "turno": "Madrugada",
                "tem_obs": False,
            },
        )
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "turno"


def test_predict_rejects_status_outside_training_domain():
    response = run_async(
        request(
            create_app(MODEL_PATH),
            "POST",
            "/predict",
            json={
                "lote_id": "L005",
                "status_raw": "Status desconhecido",
                "turno": "A",
                "tem_obs": True,
            },
        )
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"][-1] == "status_raw"
    assert "status_raw deve ser um de" in detail["msg"]


def test_health_reports_loaded_model():
    response = run_async(request(create_app(MODEL_PATH), "GET", "/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "model_loaded": True}


def test_unavailable_model_returns_service_unavailable(tmp_path: Path):
    app = create_app(tmp_path / "modelo-ausente.pkl")

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                health = await client.get("/health")
                prediction = await client.post(
                    "/predict",
                    json={
                        "lote_id": "L003",
                        "status_raw": "Em analise",
                        "turno": "A",
                        "tem_obs": False,
                    },
                )
                return health, prediction

    health, prediction = run_async(scenario())

    assert health.status_code == 503
    assert health.json() == {"status": "unhealthy", "model_loaded": False}
    assert prediction.status_code == 503
    assert prediction.json() == {"detail": "Modelo indisponivel"}


def test_model_path_uses_env_file_and_process_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ML_MODEL_PATH", raising=False)
    (tmp_path / ".env").write_text(
        "ML_MODEL_PATH=modelos/modelo-local.pkl\n",
        encoding="utf-8",
    )

    assert resolve_model_path(tmp_path) == (
        tmp_path / "modelos" / "modelo-local.pkl"
    ).resolve()

    process_model = tmp_path / "modelo-processo.pkl"
    monkeypatch.setenv("ML_MODEL_PATH", str(process_model))
    assert resolve_model_path(tmp_path) == process_model


def test_model_is_loaded_once_during_lifespan(
    monkeypatch: pytest.MonkeyPatch,
):
    actual_model = api_module.load_model(MODEL_PATH)
    calls: list[Path] = []

    def load_once(path: Path):
        calls.append(path)
        return actual_model

    monkeypatch.setattr(api_module, "load_model", load_once)
    app = create_app(MODEL_PATH)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                assert (await client.get("/health")).status_code == 200
                assert (await client.get("/health")).status_code == 200

    run_async(scenario())

    assert calls == [MODEL_PATH]


@pytest.mark.parametrize(
    ("probability", "expected_confidence", "expected_action"),
    [
        (0.85, "alta", "valido_automatico"),
        (0.849999, "media", "revisar"),
        (0.65, "media", "revisar"),
        (0.649999, "baixa", "revisar_prioritario"),
    ],
)
def test_confidence_boundaries(
    probability: float,
    expected_confidence: str,
    expected_action: str,
):
    confidence, action = resolve_confidence("valido_automatico", probability)

    assert confidence == expected_confidence
    assert action == expected_action
