"""Objetos serializáveis produzidos pela validação RN01-RN12."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class RegistroValidado:
    """Registro original acrescido da classificação rastreável da validação."""

    campos_originais: Mapping[str, Any]
    status_original: str
    status_normalizado: str
    classificacao: str
    motivo: str
    regras_violadas: tuple[str, ...]
    data_referencia: str
    aba_origem: str
    linha_origem: int

    def __post_init__(self) -> None:
        snapshot = MappingProxyType(dict(self.campos_originais))
        object.__setattr__(self, "campos_originais", snapshot)
        object.__setattr__(self, "regras_violadas", tuple(self.regras_violadas))

    def to_dict(self) -> dict[str, Any]:
        """Serializa o snapshot original sem colisão com os metadados."""
        return {
            "campos_originais": dict(self.campos_originais),
            "status_original": self.status_original,
            "status_normalizado": self.status_normalizado,
            "classificacao": self.classificacao,
            "motivo": self.motivo,
            "regras_violadas": list(self.regras_violadas),
            "data_referencia": self.data_referencia,
            "aba_origem": self.aba_origem,
            "linha_origem": self.linha_origem,
        }
