"""Operaciones de tiempo reutilizables por los comandos.

Actúan sobre Elementos ya retirados del capítulo (los comandos los retiran,
los cambian y los vuelven a colocar validando reglas). Respetan que los
keyframes son relativos al inicio del Elemento.
"""

from __future__ import annotations

import copy
import math
from enum import Enum
from typing import Callable

from editor.core.comandos.comando import EdicionRechazada
from editor.core.modelo.capa import Capa
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.keyframe import Keyframe
from editor.core.tiempo import granularidad


class Alcance(Enum):
    """Hasta dónde llega un ripple (PROJECT.md, 6.5)."""

    MINUTO = "minuto"
    CAPITULO = "capitulo"


class ModoColocacion(Enum):
    """Qué pasa si un Elemento cae sobre otros de su capa (PROJECT.md, 24.1)."""

    RECHAZAR = "rechazar"
    SOBRESCRIBIR = "sobrescribir"
    INSERTAR = "insertar"


# --- Keyframes -------------------------------------------------------------------------

def fijar_keyframe_en(elemento: Elemento, f_local: int) -> None:
    """Pone en f_local un keyframe con el valor que cada pista tiene ahí (antes de cortar)."""
    for propiedad, pista in elemento.animacion.pistas.items():
        if pista.vacia or pista.obtener(f_local) is not None:
            continue
        if pista.keyframes[0].f < f_local < pista.keyframes[-1].f:
            anterior = max((k for k in pista if k.f < f_local), key=lambda k: k.f)
            pista.poner(Keyframe(f_local, pista.valor_en(f_local, 0.0), anterior.curva, anterior.controles))
    for efecto in elemento.efectos:
        for pista in efecto.animacion.pistas.values():
            if not pista.vacia and pista.keyframes[0].f < f_local < pista.keyframes[-1].f and pista.obtener(f_local) is None:
                anterior = max((k for k in pista if k.f < f_local), key=lambda k: k.f)
                pista.poner(Keyframe(f_local, pista.valor_en(f_local, 0.0), anterior.curva, anterior.controles))


def _desplazar_keyframes(elemento: Elemento, delta: int) -> None:
    elemento.animacion = elemento.animacion.desplazada(delta)
    for efecto in elemento.efectos:
        efecto.animacion = efecto.animacion.desplazada(delta)


# --- Recortar y dividir ---------------------------------------------------------------------

def recortar_inicio(elemento: Elemento, nuevo_inicio: int) -> None:
    """Mueve el borde izquierdo sin mover el contenido en pantalla (trim de entrada)."""
    delta = nuevo_inicio - elemento.inicio
    if delta == 0:
        return
    if delta >= elemento.duracion:
        raise EdicionRechazada("El recorte dejaría el Elemento sin duración.")
    tiempo = elemento.tiempo
    if not tiempo.congelado and tiempo.velocidad > 0:
        # Con rampa, lo recorrido hasta el corte es la integral de la velocidad.
        avance = elemento.avance_fuente(delta) if (delta > 0 and elemento.con_rampa) else delta * tiempo.velocidad
        nueva_entrada = tiempo.fuente_entrada + math.floor(avance + 1e-9)
        if nueva_entrada < 0:
            raise EdicionRechazada("No hay más material de la fuente antes de la entrada.")
        tiempo.fuente_entrada = nueva_entrada
    if delta > 0:
        fijar_keyframe_en(elemento, delta)
    _desplazar_keyframes(elemento, -delta)
    tiempo.inicio = nuevo_inicio
    tiempo.duracion -= delta
    if delta > 0 and elemento.transicion_entrada is not None:
        elemento.transicion_entrada = None


def recortar_fin(elemento: Elemento, nuevo_fin: int) -> None:
    """Mueve el borde derecho (trim de salida)."""
    if nuevo_fin <= elemento.inicio:
        raise EdicionRechazada("El recorte dejaría el Elemento sin duración.")
    if nuevo_fin < elemento.fin:
        fijar_keyframe_en(elemento, nuevo_fin - elemento.inicio)
    elemento.tiempo.duracion = nuevo_fin - elemento.inicio


def dividir(elemento: Elemento, f: int, id_nuevo: str) -> Elemento:
    """Corta en f: `elemento` queda como la parte izquierda y se devuelve la derecha."""
    if not elemento.inicio < f < elemento.fin:
        raise EdicionRechazada("El punto de corte debe estar dentro del Elemento.")
    derecha = copy.deepcopy(elemento)
    derecha.id = id_nuevo
    derecha.archivo = None
    derecha.transicion_entrada = None
    recortar_inicio(derecha, f)
    recortar_fin(elemento, f)
    return derecha


# --- Rangos y desplazamientos -------------------------------------------------------------

def mismo_espacio(a: Elemento, b: Elemento) -> bool:
    """Misma capa y mismo espacio (minutos o Global)."""
    return a.capa == b.capa and a.en_global == b.en_global


def elementos_en_capa(capitulo: Capitulo, capa: Capa, en_global: bool) -> list[Elemento]:
    fuente = capitulo.global_ if en_global else capitulo.elementos_de_minutos()
    return sorted((e for e in fuente if e.capa == capa), key=lambda e: e.inicio)


def abrir_hueco(
    capitulo: Capitulo,
    capa: Capa,
    en_global: bool,
    inicio: int,
    fin: int,
    ids_nuevos: Callable[[], str],
    ignorar: set[str] | None = None,
) -> tuple[list[Elemento], list[Elemento], list[Elemento]]:
    """Deja libre [inicio, fin) en una capa (modo sobrescribir).

    Devuelve (modificados, quitados, creados); los modificados y creados quedan
    fuera del capítulo para que el comando los vuelva a colocar.
    """
    ignorar = ignorar or set()
    modificados: list[Elemento] = []
    quitados: list[Elemento] = []
    creados: list[Elemento] = []
    for existente in elementos_en_capa(capitulo, capa, en_global):
        if existente.id in ignorar or existente.fin <= inicio or fin <= existente.inicio:
            continue
        if not capitulo.editable(existente):
            raise EdicionRechazada(f"El Elemento {existente.id} está bloqueado y ocupa ese lugar.")
        capitulo.contenedor_de(existente).elementos.pop(existente.id, None)
        if inicio <= existente.inicio and existente.fin <= fin:
            quitados.append(existente)
        elif existente.inicio < inicio and fin < existente.fin:
            derecha = dividir(existente, fin, ids_nuevos())
            recortar_fin(existente, inicio)
            modificados.append(existente)
            creados.append(derecha)
        elif existente.inicio < inicio:
            recortar_fin(existente, inicio)
            modificados.append(existente)
        else:
            recortar_inicio(existente, fin)
            modificados.append(existente)
    return modificados, quitados, creados


def a_desplazar(
    capitulo: Capitulo,
    desde: int,
    alcance: Alcance,
    minuto: int,
    capa: Capa | None = None,
    ignorar: set[str] | None = None,
) -> list[Elemento]:
    """Elementos de minutos que empiezan en `desde` o después, dentro del alcance."""
    ignorar = ignorar or set()
    resultado = []
    for elemento in capitulo.elementos_de_minutos():
        if elemento.id in ignorar or elemento.inicio < desde:
            continue
        if capa is not None and elemento.capa != capa:
            continue
        if alcance is Alcance.MINUTO and elemento.minuto_inicio != minuto:
            continue
        resultado.append(elemento)
    return resultado


def desplazar(elementos: list[Elemento], delta: int) -> None:
    for elemento in elementos:
        nuevo = elemento.inicio + delta
        if nuevo < 0 or not granularidad.dentro_del_capitulo(nuevo):
            raise EdicionRechazada("El desplazamiento saca Elementos fuera del capítulo.")
        elemento.tiempo.inicio = nuevo

