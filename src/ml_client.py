"""Cliente resiliente para o serviço de classificação de lotes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import time
from typing import Callable, Literal, Mapping, cast
from urllib.request import Request, urlopen

from src.logging_config import LOGGER_NAME


LOGGER = logging.getLogger(LOGGER_NAME)
CIRCUIT_BREAKER_FAILURE_LIMIT = 5

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
CONFIDENCE_LEVELS = frozenset({"alta", "media", "baixa"})
RECOMMENDED_ACTIONS = frozenset(
    {
        "valido_automatico",
        "recusar_automatico",
        "revisar",
        "revisar_prioritario",
    }
)

Transport = Callable[[str, bytes, float], bytes]
Clock = Callable[[], float]


@dataclass(frozen=True)
class MLPrediction:
    classe: PredictionClass
    probabilidade: float
    nivel_confianca: ConfidenceLevel
    acao: RecommendedAction
    latencia_ms: float


def post_json(url: str, payload: bytes, timeout: float) -> bytes:
    """Executa um POST JSON usando apenas a biblioteca padrão."""
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        status = int(getattr(response, "status", 200))
        if not 200 <= status < 300:
            raise RuntimeError(f"Resposta HTTP não bem-sucedida: {status}")
        return response.read()


class MLClient:
    """Consome a API sem propagar falhas técnicas ao processamento."""

    def __init__(
        self,
        api_url: str,
        timeout_seconds: float,
        *,
        transport: Transport = post_json,
        clock: Clock = time.monotonic,
    ) -> None:
        self.predict_url = f"{api_url.rstrip('/')}/predict"
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self._clock = clock
        self._consecutive_failures = 0
        self._circuit_open = False

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open

    def reset_circuit_breaker(self) -> None:
        """Reabre a comunicação de forma explícita para operação e testes."""
        self._consecutive_failures = 0
        self._circuit_open = False

    def classificar(
        self,
        *,
        lote_id: str,
        status_raw: str,
        turno: str,
        tem_obs: bool,
    ) -> MLPrediction | None:
        if self._circuit_open:
            return None

        started_at = self._clock()
        try:
            payload = json.dumps(
                {
                    "lote_id": lote_id,
                    "status_raw": status_raw,
                    "turno": turno,
                    "tem_obs": tem_obs,
                }
            ).encode("utf-8")
            raw_response = self._transport(
                self.predict_url,
                payload,
                self.timeout_seconds,
            )
            latency_ms = self._elapsed_ms(started_at)
            prediction = self._parse_prediction(raw_response, latency_ms)
        except Exception as exc:
            self._register_failure(
                lote_id=lote_id,
                error_type=type(exc).__name__,
                latency_ms=self._elapsed_ms(started_at),
            )
            return None

        self._consecutive_failures = 0
        self._log_prediction(lote_id, prediction)
        return prediction

    def _elapsed_ms(self, started_at: float) -> float:
        return round(max(0.0, (self._clock() - started_at) * 1000), 3)

    @staticmethod
    def _parse_prediction(raw_response: bytes, latency_ms: float) -> MLPrediction:
        decoded = json.loads(raw_response.decode("utf-8"))
        if not isinstance(decoded, Mapping):
            raise ValueError("Resposta da API deve ser um objeto JSON")

        required = {
            "classe",
            "probabilidade",
            "nivel_confianca",
            "acao",
        }
        if not required.issubset(decoded):
            raise ValueError("Resposta da API não contém os campos obrigatórios")

        predicted_class = str(decoded["classe"])
        confidence = str(decoded["nivel_confianca"])
        action = str(decoded["acao"])
        probability_value = decoded["probabilidade"]
        if isinstance(probability_value, bool) or not isinstance(
            probability_value,
            (int, float),
        ):
            raise ValueError("Probabilidade inválida")
        probability = float(probability_value)

        if predicted_class not in PREDICTION_CLASSES:
            raise ValueError("Classe inválida")
        if confidence not in CONFIDENCE_LEVELS:
            raise ValueError("Nível de confiança inválido")
        if action not in RECOMMENDED_ACTIONS:
            raise ValueError("Ação inválida")
        if not 0 <= probability <= 1:
            raise ValueError("Probabilidade fora do intervalo esperado")

        return MLPrediction(
            classe=cast(PredictionClass, predicted_class),
            probabilidade=probability,
            nivel_confianca=cast(ConfidenceLevel, confidence),
            acao=cast(RecommendedAction, action),
            latencia_ms=latency_ms,
        )

    def _register_failure(
        self,
        *,
        lote_id: str,
        error_type: str,
        latency_ms: float,
    ) -> None:
        self._consecutive_failures += 1
        LOGGER.warning(
            "Falha tratada na comunicação com a API ML",
            extra={
                "evento": "FALHA_COMUNICACAO_ML",
                "formulario": "MLClient",
                "status": "FALLBACK",
                "usuario": "sistema",
                "lote_id": lote_id,
                "latencia_ms": latency_ms,
                "falhas_consecutivas": self._consecutive_failures,
                "ml_error_type": error_type,
            },
        )
        if self._consecutive_failures == CIRCUIT_BREAKER_FAILURE_LIMIT:
            self._circuit_open = True
            LOGGER.error(
                "Circuit breaker da API ML aberto após cinco falhas consecutivas",
                extra={
                    "evento": "CIRCUIT_BREAKER_ML",
                    "formulario": "MLClient",
                    "status": "OPEN",
                    "usuario": "sistema",
                    "lote_id": lote_id,
                    "falhas_consecutivas": self._consecutive_failures,
                },
            )

    @staticmethod
    def _log_prediction(lote_id: str, prediction: MLPrediction) -> None:
        LOGGER.info(
            "Decisão recebida da API ML",
            extra={
                "evento": "DECISAO_ML",
                "formulario": "MLClient",
                "status": "SUCCESS",
                "usuario": "sistema",
                "lote_id": lote_id,
                "classe": prediction.classe,
                "probabilidade": prediction.probabilidade,
                "nivel_confianca": prediction.nivel_confianca,
                "acao": prediction.acao,
                "latencia_ms": prediction.latencia_ms,
            },
        )
