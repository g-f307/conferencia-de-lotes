"""Classificação opcional da causa de divergências a partir de texto livre.

Este módulo é a única fronteira HTTP da classificação por observação. Falhas do
serviço, respostas inválidas e baixa confiança sempre viram resultados seguros;
nenhuma delas é propagada ao pipeline.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from src.config import Settings
from src.logging_config import LOGGER_NAME
from src.ml_client import Transport, post_json

LOGGER = logging.getLogger(LOGGER_NAME)
NAO_CLASSIFICADO = "nao_classificado"

OrigemDecisao = Literal["ml", "fallback"]
MotivoFallback = Literal[
    "ml_desabilitado",
    "observacao_ausente",
    "indisponibilidade",
    "timeout",
    "baixa_confianca",
    "resposta_invalida",
]
Clock = Callable[[], float]


@dataclass(frozen=True)
class PredicaoCausa:
    """Resposta mínima esperada de um provedor de classificação textual."""

    causa_provavel: str
    confianca_ml: float

    def __post_init__(self) -> None:
        causa = str(self.causa_provavel).strip()
        if not causa:
            raise ValueError("causa_provavel deve ser um texto não vazio")
        if isinstance(self.confianca_ml, bool) or not isinstance(
            self.confianca_ml,
            (int, float),
        ):
            raise TypeError("confianca_ml deve ser numérica")
        confianca = float(self.confianca_ml)
        if not math.isfinite(confianca) or not 0 <= confianca <= 1:
            raise ValueError("confianca_ml deve estar entre 0 e 1")
        object.__setattr__(self, "causa_provavel", causa)
        object.__setattr__(self, "confianca_ml", confianca)


@dataclass(frozen=True)
class ResultadoClassificacaoDivergencia:
    """Resultado seguro consumido pelas demais etapas do pipeline."""

    causa_provavel: str
    confianca_ml: float | None
    origem_decisao: OrigemDecisao
    motivo_fallback: MotivoFallback | None
    latencia_ms: float


class ProvedorClassificacaoDivergencia(Protocol):
    """Contrato injetável para API real ou mock controlado."""

    def classificar(
        self,
        observacao: str,
        timeout_seconds: float,
    ) -> PredicaoCausa: ...


class ProvedorHTTPClassificacaoDivergencia:
    """Cliente HTTP do endpoint textual, mantido dentro desta fronteira."""

    def __init__(
        self,
        api_url: str,
        *,
        transport: Transport = post_json,
    ) -> None:
        self.predict_url = f"{api_url.rstrip('/')}/predict-divergencia"
        self._transport = transport

    def classificar(
        self,
        observacao: str,
        timeout_seconds: float,
    ) -> PredicaoCausa:
        payload = json.dumps(
            {"observacao": observacao},
            ensure_ascii=False,
        ).encode("utf-8")
        raw_response = self._transport(
            self.predict_url,
            payload,
            timeout_seconds,
        )
        decoded = json.loads(raw_response.decode("utf-8"))
        if not isinstance(decoded, Mapping):
            raise TypeError("Resposta do classificador deve ser um objeto JSON")
        if not {"causa_provavel", "confianca_ml"}.issubset(decoded):
            raise ValueError("Resposta do classificador está incompleta")
        return PredicaoCausa(
            causa_provavel=decoded["causa_provavel"],
            confianca_ml=decoded["confianca_ml"],
        )


class ClassificadorDivergencia:
    """Sugere uma causa sem tornar o ML uma dependência crítica."""

    def __init__(
        self,
        *,
        enabled: bool,
        confianca_minima: float,
        timeout_seconds: float,
        provedor: ProvedorClassificacaoDivergencia | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        if isinstance(confianca_minima, bool) or not isinstance(
            confianca_minima,
            (int, float),
        ):
            raise TypeError("confianca_minima deve ser numérica")
        if not math.isfinite(float(confianca_minima)) or not 0 <= confianca_minima <= 1:
            raise ValueError("confianca_minima deve estar entre 0 e 1")
        if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
            raise ValueError("timeout_seconds deve ser maior que zero")
        if enabled and provedor is None:
            raise ValueError("provedor deve ser informado quando o ML está habilitado")

        self.enabled = enabled
        self.confianca_minima = float(confianca_minima)
        self.timeout_seconds = float(timeout_seconds)
        self.provedor = provedor
        self._clock = clock

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        transport: Transport = post_json,
        clock: Clock = time.monotonic,
    ) -> ClassificadorDivergencia:
        """Constrói a fronteira usando somente configurações validadas."""
        settings.validate()
        timeout_seconds = settings.ml_timeout_seconds
        confianca_minima = settings.ml_confianca_minima
        if settings.ml_enabled:
            assert timeout_seconds is not None
            assert confianca_minima is not None
        else:
            if timeout_seconds is None or timeout_seconds <= 0:
                timeout_seconds = 3.0
            if confianca_minima is None or not 0 <= confianca_minima <= 1:
                confianca_minima = 0.85
        provedor = (
            ProvedorHTTPClassificacaoDivergencia(
                settings.ml_api_url,
                transport=transport,
            )
            if settings.ml_enabled
            else None
        )
        return cls(
            enabled=settings.ml_enabled,
            confianca_minima=confianca_minima,
            timeout_seconds=timeout_seconds,
            provedor=provedor,
            clock=clock,
        )

    def classificar(self, observacao: str | None) -> ResultadoClassificacaoDivergencia:
        """Classifica a observação ou retorna fallback com motivo específico."""
        if not self.enabled:
            return self._fallback("ml_desabilitado", latencia_ms=0.0)

        texto = str(observacao or "").strip()
        if not texto:
            return self._fallback("observacao_ausente", latencia_ms=0.0)

        started_at = self._clock()
        try:
            assert self.provedor is not None
            predicao = self.provedor.classificar(texto, self.timeout_seconds)
            if not isinstance(predicao, PredicaoCausa):
                raise TypeError("Provedor retornou um contrato inesperado")
        except TimeoutError:
            return self._fallback("timeout", latencia_ms=self._elapsed_ms(started_at))
        except (TypeError, ValueError):
            return self._fallback(
                "resposta_invalida",
                latencia_ms=self._elapsed_ms(started_at),
            )
        # A fronteira deve converter qualquer falha do provedor em fallback.
        except Exception:  # noqa: BLE001
            return self._fallback(
                "indisponibilidade",
                latencia_ms=self._elapsed_ms(started_at),
            )

        latencia_ms = self._elapsed_ms(started_at)
        if predicao.confianca_ml < self.confianca_minima:
            return self._fallback(
                "baixa_confianca",
                confianca_ml=predicao.confianca_ml,
                latencia_ms=latencia_ms,
            )

        resultado = ResultadoClassificacaoDivergencia(
            causa_provavel=predicao.causa_provavel,
            confianca_ml=predicao.confianca_ml,
            origem_decisao="ml",
            motivo_fallback=None,
            latencia_ms=latencia_ms,
        )
        LOGGER.info(
            "Causa provável sugerida pelo classificador de divergências",
            extra={
                "evento": "CLASSIFICACAO_DIVERGENCIA_ML",
                "formulario": "ClassificadorDivergencia",
                "status": "SUCCESS",
                "usuario": "sistema",
                "causa_provavel": resultado.causa_provavel,
                "confianca_ml": resultado.confianca_ml,
                "origem_decisao": resultado.origem_decisao,
                "latencia_ms": resultado.latencia_ms,
            },
        )
        return resultado

    def _elapsed_ms(self, started_at: float) -> float:
        return round(max(0.0, (self._clock() - started_at) * 1000), 3)

    @staticmethod
    def _fallback(
        motivo: MotivoFallback,
        *,
        confianca_ml: float | None = None,
        latencia_ms: float,
    ) -> ResultadoClassificacaoDivergencia:
        resultado = ResultadoClassificacaoDivergencia(
            causa_provavel=NAO_CLASSIFICADO,
            confianca_ml=confianca_ml,
            origem_decisao="fallback",
            motivo_fallback=motivo,
            latencia_ms=latencia_ms,
        )
        LOGGER.warning(
            "Fallback seguro aplicado pelo classificador de divergências: %s",
            motivo,
            extra={
                "evento": "FALLBACK_CLASSIFICADOR_DIVERGENCIA",
                "formulario": "ClassificadorDivergencia",
                "status": "FALLBACK",
                "usuario": "sistema",
                "causa_provavel": resultado.causa_provavel,
                "confianca_ml": resultado.confianca_ml,
                "origem_decisao": resultado.origem_decisao,
                "motivo_fallback": resultado.motivo_fallback,
                "latencia_ms": resultado.latencia_ms,
            },
        )
        return resultado
