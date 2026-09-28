"""Transiciones: se guardan en el Elemento entrante (PROJECT.md, 8.3).

Su duración es el solape permitido con el Elemento anterior de la misma capa.
Cada tipo tiene un descriptor (como los efectos) para que la interfaz y los
plugins (E23) lo traten igual.
"""

from __future__ import annotations

from dataclasses import dataclass

FUNDIDO = "fundido"
DESLIZAMIENTO = "deslizamiento"
ZOOM = "zoom"
BARRIDO = "barrido"
NEGRO = "negro"   # fundido a negro: sale el anterior, pasa por negro, entra el nuevo
TIPOS_TRANSICION = (FUNDIDO, DESLIZAMIENTO, ZOOM, BARRIDO, NEGRO)
DIRECCIONES = ("izquierda", "derecha", "arriba", "abajo")


@dataclass(frozen=True)
class DescriptorTransicion:
    tipo: str
    etiqueta: str
    usa_direccion: bool = False


# Registro ampliable: los plugins (E23) agregan sus tipos con `registrar_tipo_transicion`.
_DESCRIPTORES: dict[str, DescriptorTransicion] = {
    d.tipo: d for d in (
        DescriptorTransicion(FUNDIDO, "Fundido"),
        DescriptorTransicion(DESLIZAMIENTO, "Deslizamiento", usa_direccion=True),
        DescriptorTransicion(ZOOM, "Zoom"),
        DescriptorTransicion(BARRIDO, "Barrido", usa_direccion=True),
        DescriptorTransicion(NEGRO, "Fundido a negro"),
    )
}


def registrar_tipo_transicion(tipo: str, descriptor: DescriptorTransicion | None = None) -> None:
    _DESCRIPTORES[tipo] = descriptor or _DESCRIPTORES.get(tipo) or DescriptorTransicion(tipo, tipo)


def tipos_transicion() -> list[str]:
    return sorted(_DESCRIPTORES)


def descriptor_transicion(tipo: str) -> DescriptorTransicion:
    return _DESCRIPTORES.get(tipo) or DescriptorTransicion(tipo, tipo)


DURACION_POR_DEFECTO = 12  # medio segundo


@dataclass(frozen=True)
class Transicion:
    tipo: str = FUNDIDO
    duracion: int = DURACION_POR_DEFECTO
    # Dirección para deslizamiento y barrido.
    direccion: str = "izquierda"

    def __post_init__(self) -> None:
        if self.tipo not in _DESCRIPTORES:
            raise ValueError(f"Transición desconocida: {self.tipo!r}")
        if self.duracion <= 0:
            raise ValueError("La duración de la transición debe ser positiva.")
        if self.direccion not in DIRECCIONES:
            raise ValueError(f"Dirección de transición desconocida: {self.direccion!r}")
