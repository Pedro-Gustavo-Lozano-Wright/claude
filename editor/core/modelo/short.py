"""Shorts: recortes verticales 9:16 de un rango del capítulo (PROJECT.md, 13.5).

La ventana vertical se mueve en horizontal sobre el lienzo 16:9 y puede
animarse para seguir la acción. El render la recompone a 720×1280.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from editor.core.espacio.geometria import Rect
from editor.core.espacio.lienzo import LIENZO, Lienzo
from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO
from editor.core.modelo.errores import ErrorModelo
from editor.core.modelo.keyframe import Animacion
from editor.core.tiempo import granularidad
from editor.core.tiempo.granularidad import Duracion, Instante
from editor.core.tiempo.nomenclatura import NombreShort


@dataclass
class VentanaVertical:
    x: float = LIENZO.x_ventana_centrada()
    zoom: float = 1.0
    animacion: Animacion = field(default_factory=Animacion)

    def __post_init__(self) -> None:
        if self.zoom < 1.0:
            raise ErrorModelo("El zoom de la ventana vertical no puede ser menor que 1.")

    def rect_en(self, f_local: float, lienzo: Lienzo = LIENZO) -> Rect:
        """Ventana en el fotograma f, relativo al inicio del Short."""
        x = self.animacion.valor("x", f_local, self.x)
        zoom = max(1.0, self.animacion.valor("zoom", f_local, self.zoom))
        return lienzo.ventana_vertical(x, zoom)


@dataclass
class RegistroRenderShort:
    version: int
    huella: str


@dataclass
class Short:
    id: str
    nombre: str
    inicio: int
    duracion: int
    ventana: VentanaVertical = field(default_factory=VentanaVertical)
    ultimo_render: RegistroRenderShort | None = None

    def __post_init__(self) -> None:
        if self.duracion <= 0:
            raise ErrorModelo("La duración del Short debe ser positiva.")
        if not 0 <= self.inicio or self.fin > FOTOGRAMAS_POR_CAPITULO:
            raise ErrorModelo("Un Short no puede salir de su capítulo.")

    @property
    def fin(self) -> int:
        return self.inicio + self.duracion

    @property
    def minutos_cruzados(self) -> range:
        return granularidad.minutos_cruzados(self.inicio, self.fin)

    def rect_en(self, f: int) -> Rect:
        """Ventana en el fotograma f del capítulo."""
        return self.ventana.rect_en(f - self.inicio)

    def nombre_archivo(self) -> NombreShort:
        return NombreShort(Instante(self.inicio), Duracion(self.duracion), self.nombre, self.id)

    @property
    def siguiente_version_render(self) -> int:
        return 1 if self.ultimo_render is None else self.ultimo_render.version + 1
