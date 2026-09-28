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

# Registro ampliable: los plugins (E23) agregan sus tipos aquí.
_tipos_registrados: set[str] = set(TIPOS_TRANSICION)


def registrar_tipo_transicion(tipo: str) -> None:
    _tipos_registrados.add(tipo)


def tipos_transicion() -> list[str]:
    return sorted(_tipos_registrados)


DURACION_POR_DEFECTO = 12  # medio segundo


@dataclass(frozen=True)
class Transicion:
    tipo: str = FUNDIDO
    duracion: int = DURACION_POR_DEFECTO
    # Dirección para deslizamiento y barrido: "izquierda", "derecha", "arriba", "abajo".
    direccion: str = "izquierda"

    def __post_init__(self) -> None:
        if self.tipo not in _tipos_registrados:
            raise ValueError(f"Transición desconocida: {self.tipo!r}")
        if self.duracion <= 0:
            raise ValueError("La duración de la transición debe ser positiva.")
