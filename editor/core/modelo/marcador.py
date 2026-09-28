"""Marcadores y estado de las capas del capítulo.

Marcador: una nota en un fotograma del capítulo (también es un punto de imán).
EstadoCapa: ocultar, silenciar, bloquear o escuchar en solo una capa. Las
capas de Global son un espacio aparte: su clave lleva el prefijo "G".
"""

from __future__ import annotations

from dataclasses import dataclass

COLORES_MARCADOR = ("rojo", "naranja", "amarillo", "verde", "azul", "violeta")


@dataclass
class Marcador:
    f: int
    nombre: str = ""
    nota: str = ""
    color: str = "amarillo"

    def __post_init__(self) -> None:
        if self.f < 0:
            raise ValueError("Un marcador no puede estar en un fotograma negativo.")
        if self.color not in COLORES_MARCADOR:
            raise ValueError(f"Color de marcador desconocido: {self.color!r}")


@dataclass
class EstadoCapa:
    visible: bool = True
    silenciada: bool = False
    bloqueada: bool = False
    solo: bool = False


def clave_capa(codigo: str, en_global: bool) -> str:
    return f"G{codigo}" if en_global else codigo
