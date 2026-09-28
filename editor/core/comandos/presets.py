"""Presets de animación (E19): Ken Burns, entradas y salidas de clips, estabilización.

Todos producen comandos ya existentes (keyframes y ancla) agrupados en un solo
paso de deshacer. Los keyframes quedan editables como cualquier otro.
"""

from __future__ import annotations

from editor.core.comandos.agregar_keyframe import PonerKeyframe
from editor.core.comandos.compuesto import ComandoCompuesto
from editor.core.comandos.transformar_elemento import MoverAncla
from editor.core.espacio.lienzo import LIENZO
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.errores import ErrorModelo
from editor.core.modelo.keyframe import Keyframe
from editor.core.utiles.interpolacion import EASE_IN_OUT as EASE_IN_OUT_NOMBRE

ANIMACIONES_CLIP = ("fundido", "deslizar", "zoom")


def _centrar_ancla(capitulo: int, elemento: Elemento) -> list:
    """Ancla al centro del Elemento (escalar y girar alrededor del centro) sin moverlo en pantalla."""
    if not elemento.ancho or not elemento.alto:
        raise ErrorModelo("Este preset necesita un Elemento con imagen (no un texto ni un audio).")
    centro_x, centro_y = elemento.ancho / 2, elemento.alto / 2
    if (elemento.espacio.ancla_x, elemento.espacio.ancla_y) == (centro_x, centro_y):
        return []
    return [MoverAncla(capitulo, elemento.id, centro_x, centro_y)]


def _base_con_ancla_centrada(elemento: Elemento):
    """Transform que tendrá el Elemento tras centrar el ancla (para calcular los keyframes)."""
    if not elemento.ancho or not elemento.alto:
        return elemento.espacio
    return elemento.espacio.mover_ancla(elemento.ancho / 2, elemento.alto / 2)


def ken_burns(capitulo: int, elemento: Elemento, zoom: float = 1.15, desplazamiento_x: float = 0.0,
              desplazamiento_y: float = 0.0) -> ComandoCompuesto:
    """Acercamiento lento de principio a fin (con desplazamiento opcional en px del lienzo)."""
    if elemento.duracion < 2:
        raise ErrorModelo("El Elemento es demasiado corto para un Ken Burns.")
    comandos = _centrar_ancla(capitulo, elemento)
    base = _base_con_ancla_centrada(elemento)
    ultimo = elemento.duracion - 1
    for propiedad, inicio, fin in (
        ("escala_x", base.escala_x, base.escala_x * zoom),
        ("escala_y", base.escala_y, base.escala_y * zoom),
        ("x", base.x, base.x + desplazamiento_x),
        ("y", base.y, base.y + desplazamiento_y),
    ):
        if inicio == fin and propiedad in ("x", "y"):
            continue
        comandos.append(PonerKeyframe(capitulo, elemento.id, propiedad, Keyframe(0, inicio, EASE_IN_OUT_NOMBRE)))
        comandos.append(PonerKeyframe(capitulo, elemento.id, propiedad, Keyframe(ultimo, fin)))
    return ComandoCompuesto("Ken Burns", comandos)


def animacion_clip(capitulo: int, elemento: Elemento, tipo: str, entrada: bool, duracion: int = 12) -> ComandoCompuesto:
    """Entrada (desde el comienzo) o salida (hasta el final) de un clip: fundido, deslizar o zoom."""
    if tipo not in ANIMACIONES_CLIP:
        raise ValueError(f"Animación desconocida: {tipo!r}")
    duracion = max(1, min(duracion, elemento.duracion - 1))
    if elemento.duracion < 2:
        raise ErrorModelo("El Elemento es demasiado corto para animarlo.")
    a, b = (0, duracion) if entrada else (elemento.duracion - 1 - duracion, elemento.duracion - 1)
    comandos = _centrar_ancla(capitulo, elemento) if tipo == "zoom" else []
    base = _base_con_ancla_centrada(elemento) if tipo == "zoom" else elemento.espacio

    def par(propiedad: str, oculto: float, visible: float) -> None:
        valores = (oculto, visible) if entrada else (visible, oculto)
        comandos.append(PonerKeyframe(capitulo, elemento.id, propiedad, Keyframe(a, valores[0], EASE_IN_OUT_NOMBRE)))
        comandos.append(PonerKeyframe(capitulo, elemento.id, propiedad, Keyframe(b, valores[1])))

    if tipo == "fundido":
        par("opacidad", 0.0, base.opacidad)
    elif tipo == "deslizar":
        par("x", base.x - LIENZO.ancho, base.x)
    else:
        par("escala_x", base.escala_x * 0.8, base.escala_x)
        par("escala_y", base.escala_y * 0.8, base.escala_y)
        par("opacidad", 0.0, base.opacidad)
    nombre = {"fundido": "Fundido", "deslizar": "Deslizar", "zoom": "Zoom"}[tipo]
    return ComandoCompuesto(f"{nombre} de {'entrada' if entrada else 'salida'}", comandos)


def estabilizar(capitulo: int, elemento: Elemento, correcciones: dict[int, tuple[float, float, float]],
                margen: float = 1.06) -> ComandoCompuesto:
    """Keyframes de x, y, rotación (y escala para ocultar bordes) por fotograma.

    `correcciones`: fotograma local → (dx, dy, grados) en píxeles del **archivo fuente**;
    se pasan a píxeles del lienzo con la escala actual del Elemento.
    """
    if not correcciones:
        raise ErrorModelo("No hay movimiento que corregir.")
    comandos = _centrar_ancla(capitulo, elemento)
    base = _base_con_ancla_centrada(elemento)
    for propiedad in ("escala_x", "escala_y"):
        comandos.append(PonerKeyframe(capitulo, elemento.id, propiedad,
                                      Keyframe(0, getattr(base, propiedad) * margen)))
    for f_local, (dx, dy, grados) in sorted(correcciones.items()):
        if not 0 <= f_local < elemento.duracion:
            continue
        comandos.append(PonerKeyframe(capitulo, elemento.id, "x", Keyframe(f_local, base.x + dx * base.escala_x * margen)))
        comandos.append(PonerKeyframe(capitulo, elemento.id, "y", Keyframe(f_local, base.y + dy * base.escala_y * margen)))
        comandos.append(PonerKeyframe(capitulo, elemento.id, "rotacion", Keyframe(f_local, base.rotacion + grados)))
    return ComandoCompuesto("Estabilizar", comandos)
