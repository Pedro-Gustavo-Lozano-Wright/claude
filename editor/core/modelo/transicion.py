"""Transiciones: se guardan en el Elemento entrante (PROJECT.md, 8.3).

Su duración es el solape permitido con el Elemento anterior de la misma capa.
"""

from __future__ import annotations

from dataclasses import dataclass

FUNDIDO = "fundido"
DESLIZAMIENTO = "deslizamiento"
ZOOM = "zoom"
BARRIDO = "barrido"
TIPOS_TRANSICION = (FUNDIDO, DESLIZAMIENTO, ZOOM, BARRIDO)

DURACION_POR_DEFECTO = 12  # medio segundo


@dataclass(frozen=True)
class Transicion:
    tipo: str = FUNDIDO
    duracion: int = DURACION_POR_DEFECTO
    # Dirección para deslizamiento y barrido: "izquierda", "derecha", "arriba", "abajo".
    direccion: str = "izquierda"

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS_TRANSICION:
            raise ValueError(f"Transición desconocida: {self.tipo!r}")
        if self.duracion <= 0:
            raise ValueError("La duración de la transición debe ser positiva.")
