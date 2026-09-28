"""Shorts verticales: crear, quitar, cambiar rango y ventana, keyframes (T6.8)."""

from __future__ import annotations

import copy
from dataclasses import replace

from editor.core.comandos.comando import Afectados, EdicionRechazada
from editor.core.comandos.estado_capitulo import EdicionEstadoCapitulo
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.keyframe import Keyframe
from editor.core.modelo.short import Short


class _EdicionShort(EdicionEstadoCapitulo):
    partes = ("shorts",)

    def afectados_de(self, *ids: str) -> Afectados:
        return Afectados(self.capitulo, shorts=set(ids))


class CrearShort(_EdicionShort):
    descripcion = "Crear Short"

    def __init__(self, capitulo: int, short: Short) -> None:
        super().__init__(capitulo)
        self.short = copy.deepcopy(short)

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        capitulo.agregar_short(copy.deepcopy(self.short))
        return self.afectados_de(self.short.id)


class QuitarShort(_EdicionShort):
    descripcion = "Quitar Short"

    def __init__(self, capitulo: int, id_short: str) -> None:
        super().__init__(capitulo)
        self.id_short = id_short

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        capitulo.quitar_short(self.id_short)
        return self.afectados_de(self.id_short)


class CambiarRangoShort(_EdicionShort):
    descripcion = "Cambiar rango del Short"

    def __init__(self, capitulo: int, id_short: str, inicio: int, duracion: int, nombre: str | None = None) -> None:
        super().__init__(capitulo)
        self.id_short = id_short
        self.inicio = inicio
        self.duracion = duracion
        self.nombre = nombre

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        short = capitulo.shorts.get(self.id_short)
        if short is None:
            raise EdicionRechazada(f"No hay un Short {self.id_short}.")
        capitulo.shorts[self.id_short] = Short(
            id=short.id,
            nombre=self.nombre or short.nombre,
            inicio=self.inicio,
            duracion=self.duracion,
            ventana=short.ventana,
            ultimo_render=short.ultimo_render,
        )
        return self.afectados_de(self.id_short)


class MoverVentanaShort(_EdicionShort):
    """Posición (x) y zoom base de la ventana vertical; valores absolutos."""

    descripcion = "Mover ventana del Short"

    def __init__(self, capitulo: int, id_short: str, x: float, zoom: float | None = None) -> None:
        super().__init__(capitulo)
        self.id_short = id_short
        self.x = x
        self.zoom = zoom

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        short = capitulo.shorts.get(self.id_short)
        if short is None:
            raise EdicionRechazada(f"No hay un Short {self.id_short}.")
        short.ventana = replace(short.ventana, x=self.x, zoom=self.zoom if self.zoom is not None else short.ventana.zoom)
        return self.afectados_de(self.id_short)


class PonerKeyframeVentana(_EdicionShort):
    """Keyframe de la ventana ("x" o "zoom"); `keyframe.f` es relativo al inicio del Short."""

    descripcion = "Keyframe de la ventana"

    def __init__(self, capitulo: int, id_short: str, propiedad: str, keyframe: Keyframe | None, f: int | None = None) -> None:
        super().__init__(capitulo)
        if propiedad not in ("x", "zoom"):
            raise ValueError("La ventana solo anima 'x' y 'zoom'.")
        self.id_short = id_short
        self.propiedad = propiedad
        self.keyframe = keyframe          # None = quitar el keyframe de `f`
        self.f = f

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        short = capitulo.shorts.get(self.id_short)
        if short is None:
            raise EdicionRechazada(f"No hay un Short {self.id_short}.")
        pista = short.ventana.animacion.pista(self.propiedad)
        if self.keyframe is None:
            if self.f is None or pista.quitar(self.f) is None:
                raise EdicionRechazada("No hay keyframe que quitar.")
            short.ventana.animacion.limpiar_vacias()
        else:
            if not 0 <= self.keyframe.f < short.duracion:
                raise EdicionRechazada("El keyframe cae fuera del Short.")
            pista.poner(self.keyframe)
        return self.afectados_de(self.id_short)
