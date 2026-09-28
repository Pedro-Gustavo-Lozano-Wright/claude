"""Minuto: ventana de 60 s del capítulo, con su carpeta minNN.

Un Elemento vive en el minuto donde empieza, aunque se desborde al siguiente.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from editor.core.estandar import FOTOGRAMAS_POR_MINUTO
from editor.core.modelo.composicion import Composicion
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.errores import ErrorModelo
from editor.core.tiempo import granularidad
from editor.core.tiempo.nomenclatura import codigo_minuto


class EstadoTrabajo(Enum):
    """Eje manual; VACIO se deduce solo."""

    VACIO = "vacio"
    EN_PROGRESO = "en_progreso"
    LISTO = "listo"


class EstadoRender(Enum):
    """Eje automático: compara la huella actual con la del último render."""

    SIN_RENDER = "sin_render"
    DESACTUALIZADO = "desactualizado"
    AL_DIA = "al_dia"


@dataclass
class RegistroRenderMinuto:
    version: int
    huella: str


@dataclass
class Minuto(Composicion):
    numero: int = 0
    listo: bool = False
    notas: str = ""
    ultimo_render: RegistroRenderMinuto | None = None

    @classmethod
    def nuevo(cls, numero: int) -> "Minuto":
        inicio, _ = granularidad.rango_minuto(numero)
        return cls(inicio=inicio, duracion=FOTOGRAMAS_POR_MINUTO, numero=numero)

    @property
    def codigo(self) -> str:
        return codigo_minuto(self.numero)

    def validar_ubicacion(self, elemento: Elemento) -> None:
        if elemento.en_global:
            raise ErrorModelo(f"El Elemento {elemento.id} pertenece a Global, no a {self.codigo}.")
        if not self.inicio <= elemento.inicio < self.fin:
            raise ErrorModelo(
                f"El Elemento {elemento.id} empieza en el minuto {elemento.minuto_inicio:02d}, no en {self.codigo}."
            )

    @property
    def estado_trabajo(self) -> EstadoTrabajo:
        if self.vacia:
            return EstadoTrabajo.VACIO
        return EstadoTrabajo.LISTO if self.listo else EstadoTrabajo.EN_PROGRESO

    def estado_render(self, huella_actual: str) -> EstadoRender:
        if self.ultimo_render is None:
            return EstadoRender.SIN_RENDER
        if self.ultimo_render.huella != huella_actual:
            return EstadoRender.DESACTUALIZADO
        return EstadoRender.AL_DIA

    @property
    def siguiente_version_render(self) -> int:
        return 1 if self.ultimo_render is None else self.ultimo_render.version + 1
