"""Capas: V1–V9 (video e imagen), A1–A9 (audio), T1–T9 (texto)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from editor.core.estandar import CAPAS_POR_TIPO
from editor.core.tiempo.nomenclatura import validar_codigo_capa


class TipoCapa(Enum):
    VIDEO = "V"
    AUDIO = "A"
    TEXTO = "T"


@dataclass(frozen=True)
class Capa:
    tipo: TipoCapa
    numero: int

    def __post_init__(self) -> None:
        if not 1 <= self.numero <= CAPAS_POR_TIPO:
            raise ValueError(f"Número de capa fuera de rango: {self.numero}")

    @classmethod
    def desde_codigo(cls, codigo: str) -> "Capa":
        letra, numero = validar_codigo_capa(codigo)
        return cls(TipoCapa(letra), numero)

    @property
    def codigo(self) -> str:
        return f"{self.tipo.value}{self.numero}"

    @property
    def es_visual(self) -> bool:
        return self.tipo is not TipoCapa.AUDIO

    @property
    def orden_apilado(self) -> int | None:
        """Orden de dibujo, de abajo hacia arriba: V1…V9 y después T1…T9. None para audio."""
        if self.tipo is TipoCapa.VIDEO:
            return self.numero
        if self.tipo is TipoCapa.TEXTO:
            return CAPAS_POR_TIPO + self.numero
        return None

    def __str__(self) -> str:
        return self.codigo


def todas_las_capas(tipo: TipoCapa) -> list[Capa]:
    return [Capa(tipo, numero) for numero in range(1, CAPAS_POR_TIPO + 1)]
