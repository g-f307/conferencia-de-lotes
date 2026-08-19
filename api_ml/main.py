"""API FastAPI que disponibiliza o classificador de lotes."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import re
from typing import Any, Literal, cast
import unicodedata

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import joblib
from pydantic import BaseModel, Field, field_validator
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
TURNOS = {
    "A": "A",
    "B": "B",
    "C": "C",
    "MANHA": "A",
    "TARDE": "B",
    "NOITE": "C",
}
ACCEPTED_STATUSES = frozenset(
    {
        "EM ANALISE",
        "AJUSTE DE LINHA",
        "ESPECIFICACAO EM REVISAO",
        "PENDENTE",
    }
)

PredictionClass = Literal[
    "valido_automatico",
    "revisar",
    "recusar_automatico",
]
ConfidenceLevel = Literal["alta", "media", "baixa"]
RecommendedAction = Literal[
    "valido_automatico",
    "recusar_automatico",
    "revisar",
    "revisar_prioritario",
]
PREDICTION_CLASSES = frozenset(
    {"valido_automatico", "revisar", "recusar_automatico"}
)


def normalize_text(value: object) -> str:
    """Normaliza entradas categoricas para o mesmo dominio do treinamento."""
    text = unicodedata.normalize("NFKD", str(value).strip())
    without_accents = "".join(
        char for char in text if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents).upper()


class LoteInput(BaseModel):
    """Dados publicos usados pelo modelo para classificar um lote."""

    lote_id: str = Field(min_length=1, max_length=100)
    status_raw: str = Field(min_length=1, max_length=100)
    turno: str
    tem_obs: bool

    @field_validator("lote_id")
    @classmethod
    def validate_lote_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("lote_id nao pode ser vazio")
        return normalized

    @field_validator("status_raw")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = normalize_text(value)
        if not normalized:
            raise ValueError("status_raw nao pode ser vazio")
        if normalized not in ACCEPTED_STATUSES:
            accepted = ", ".join(sorted(ACCEPTED_STATUSES))
            raise ValueError(f"status_raw deve ser um de: {accepted}")
        return normalized

    @field_validator("turno", mode="before")
    @classmethod
    def validate_turno(cls, value: object) -> str:
        normalized = normalize_text(value)
        try:
            return TURNOS[normalized]
        except KeyError as exc:
            raise ValueError(
                "turno deve ser A, B, C, Manha, Tarde ou Noite"
            ) from exc


class PredictionOutput(BaseModel):
    """Contrato estavel devolvido aos consumidores da API."""

    classe: PredictionClass
    probabilidade: float = Field(ge=0.0, le=1.0)
    nivel_confianca: ConfidenceLevel
    acao: RecommendedAction


class HealthOutput(BaseModel):
    status: Literal["healthy", "unhealthy"]
    model_loaded: bool


def resolve_confidence(
    predicted_class: PredictionClass,
    probability: float,
) -> tuple[ConfidenceLevel, RecommendedAction]:
    """Aplica os limites de confianca definidos pelo Exercicio 24-A."""
    if probability >= 0.85:
        action: RecommendedAction = predicted_class
        return "alta", action
    if probability >= 0.65:
        return "media", "revisar"
    return "baixa", "revisar_prioritario"


def resolve_model_path(project_root: Path | None = None) -> Path:
    """Resolve o artefato pelo processo, `.env` ou caminho padrao."""
    root = (project_root or PROJECT_ROOT).resolve()
    configured = os.getenv("ML_MODEL_PATH", "").strip()
    if not configured:
        configured = str(
            dotenv_values(root / ".env").get("ML_MODEL_PATH") or ""
        ).strip()
    if not configured:
        return root / "models" / "classificador_lotes.pkl"

    model_path = Path(configured).expanduser()
    return model_path if model_path.is_absolute() else (root / model_path).resolve()


def load_model(model_path: Path) -> Any:
    model = joblib.load(model_path)
    if not callable(getattr(model, "predict", None)) or not callable(
        getattr(model, "predict_proba", None)
    ):
        raise TypeError("Artefato nao implementa a interface esperada")
    return model


def create_app(model_path: Path | None = None) -> FastAPI:
    """Cria a aplicacao e carrega o modelo uma unica vez no lifespan."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        selected_path = model_path or resolve_model_path()
        application.state.model = None
        application.state.model_error = None
        try:
            application.state.model = load_model(selected_path)
        except Exception as exc:
            application.state.model_error = type(exc).__name__
            LOGGER.error(
                "Modelo de classificacao indisponivel: %s",
                application.state.model_error,
            )
        yield
        application.state.model = None

    application = FastAPI(
        title="Classificador de Lotes",
        version="1.0.0",
        lifespan=lifespan,
    )

    @application.get("/health", response_model=HealthOutput)
    async def health() -> HealthOutput | JSONResponse:
        if application.state.model is None:
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "model_loaded": False},
            )
        return HealthOutput(status="healthy", model_loaded=True)

    @application.post("/predict", response_model=PredictionOutput)
    async def predict(payload: LoteInput) -> PredictionOutput:
        model = application.state.model
        if model is None:
            raise HTTPException(status_code=503, detail="Modelo indisponivel")

        features = [[payload.status_raw, payload.turno, payload.tem_obs]]
        try:
            predicted_class = str(model.predict(features)[0])
            if predicted_class not in PREDICTION_CLASSES:
                raise ValueError("Classe devolvida pelo modelo e invalida")
            typed_class = cast(PredictionClass, predicted_class)
            probabilities = model.predict_proba(features)[0]
            classes = [str(value) for value in model.classes_]
            probability = float(probabilities[classes.index(predicted_class)])
            confidence, action = resolve_confidence(
                typed_class,
                probability,
            )
            return PredictionOutput(
                classe=typed_class,
                probabilidade=round(probability, 6),
                nivel_confianca=confidence,
                acao=action,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="Falha ao executar a predicao",
            ) from exc

    return application


app = create_app()
