"""Serviço independente para classificação de registros pelas RN01-RN12.

A classificação final respeita a precedência Erro de Entrada, Divergência,
Ambíguo e Válido. Todas as regras violadas permanecem no resultado mesmo
quando uma categoria de maior precedência determina a classificação.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from typing import Iterable, Mapping, MutableSet

from src.excel_reporting.models import RegistroValidado


CLASSIFICACAO_VALIDO = "Válido"
CLASSIFICACAO_DIVERGENCIA = "Divergência"
CLASSIFICACAO_AMBIGUO = "Ambíguo"
CLASSIFICACAO_ERRO_ENTRADA = "Erro de Entrada"

STATUS_ALIASES = {
    "OK": "APROVADO",
    "NOK": "REPROVADO",
}
STATUS_VALIDOS = {"APROVADO", "REPROVADO", "PENDENTE"}
DATA_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")

MOTIVOS = {
    "RN01": "Lote não informado",
    "RN02": "Produto não informado",
    "RN03": "Linha não informada",
    "RN04": "Status não informado",
    "RN05": "Lote não encontrado na base de referência",
    "RN09": "Status desconhecido e não normalizável",
    "RN10": "Lote reprovado sem observação",
    "RN11": "Lote repetido no mesmo dia",
    "RN12": "Data ausente ou fora do formato DD/MM/AAAA",
}

REGRAS_ERRO_ENTRADA = {"RN01", "RN02", "RN03", "RN04", "RN12"}
REGRAS_DIVERGENCIA = {"RN05", "RN10", "RN11"}
REGRAS_AMBIGUO = {"RN09"}


def _valor_ausente(value: object) -> bool:
    if value is None:
        return True
    try:
        return math.isnan(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _texto(value: object) -> str:
    return "" if _valor_ausente(value) else str(value).strip()


def _normalizar_comparacao(value: object) -> str:
    text = _texto(value).upper()
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def _normalizar_status(value: object) -> str:
    status = _normalizar_comparacao(value)
    return STATUS_ALIASES.get(status, status)


def _data_valida(value: str) -> bool:
    if not DATA_PATTERN.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%d/%m/%Y")
    except ValueError:
        return False
    return True


def _classificar(regras_violadas: Iterable[str]) -> str:
    regras = set(regras_violadas)
    if regras & REGRAS_ERRO_ENTRADA:
        return CLASSIFICACAO_ERRO_ENTRADA
    if regras & REGRAS_DIVERGENCIA:
        return CLASSIFICACAO_DIVERGENCIA
    if regras & REGRAS_AMBIGUO:
        return CLASSIFICACAO_AMBIGUO
    return CLASSIFICACAO_VALIDO


def _motivo(regras_violadas: Iterable[str]) -> str:
    regras = tuple(regras_violadas)
    if not regras:
        return "Registro válido pelas regras RN01-RN12"
    return "; ".join(f"{regra}: {MOTIVOS[regra]}" for regra in regras)


def validar_registro(
    registro: Mapping[str, object],
    lotes_referencia: Iterable[object],
    *,
    registros_vistos: MutableSet[tuple[str, str]],
    aba_origem: str = "",
    linha_origem: int = 0,
) -> RegistroValidado:
    """Valida um registro usando o contexto obrigatório da RN11."""
    original = dict(registro)
    lote_id = _texto(registro.get("lote_id"))
    produto = _texto(registro.get("produto"))
    linha = _texto(registro.get("linha"))
    status_value = registro.get("status")
    status_original = "" if _valor_ausente(status_value) else str(status_value)
    status_normalizado = _normalizar_status(status_original)
    observacao = _texto(registro.get("observacao"))
    data_referencia = _texto(registro.get("data"))
    referencias = {_texto(lote) for lote in lotes_referencia}
    regras: list[str] = []

    if not lote_id:
        regras.append("RN01")
    if not produto:
        regras.append("RN02")
    if not linha:
        regras.append("RN03")
    if not _texto(status_original):
        regras.append("RN04")
    if lote_id and lote_id not in referencias:
        regras.append("RN05")

    if status_normalizado and status_normalizado not in STATUS_VALIDOS:
        regras.append("RN09")
    if status_normalizado == "REPROVADO" and not observacao:
        regras.append("RN10")

    contexto_aba = _texto(aba_origem) or _texto(registro.get("aba_origem"))
    chave_registro = (contexto_aba, lote_id)
    if lote_id:
        if chave_registro in registros_vistos:
            regras.append("RN11")
        registros_vistos.add(chave_registro)
    if not _data_valida(data_referencia):
        regras.append("RN12")

    return RegistroValidado(
        campos_originais=original,
        status_original=status_original,
        status_normalizado=status_normalizado,
        classificacao=_classificar(regras),
        motivo=_motivo(regras),
        regras_violadas=tuple(regras),
        data_referencia=data_referencia,
        aba_origem=contexto_aba,
        linha_origem=linha_origem,
    )


class ValidationService:
    """Mantém o contexto necessário para detectar duplicidades por dia."""

    def __init__(self, lotes_referencia: Iterable[object]) -> None:
        self.lotes_referencia = tuple(lotes_referencia)
        self._registros_vistos: set[tuple[str, str]] = set()

    def validar_registro(
        self,
        registro: Mapping[str, object],
        *,
        aba_origem: str = "",
        linha_origem: int = 0,
    ) -> RegistroValidado:
        return validar_registro(
            registro,
            self.lotes_referencia,
            registros_vistos=self._registros_vistos,
            aba_origem=aba_origem,
            linha_origem=linha_origem,
        )

    def reset(self) -> None:
        """Descarta o contexto de duplicidade para iniciar outra planilha."""
        self._registros_vistos.clear()
