"""Construcción de Elementos nuevos a partir de Piezas, Brutos o texto (T6.4).

El Elemento nace con su ID ya asignado: el comando que lo agrega es así
determinista al rehacer.
"""

from __future__ import annotations

from editor.core.espacio.lienzo import LIENZO
from editor.core.espacio.transform import ORIGINAL, Transform, transform_inicial
from editor.core.estandar import FPS
from editor.core.modelo.bruto import Bruto, TipoMedio
from editor.core.modelo.capa import Capa, TipoCapa
from editor.core.modelo.elemento import Elemento, ReferenciaFuente, TiempoElemento, TipoFuente
from editor.core.modelo.errores import ErrorModelo
from editor.core.modelo.pieza import Pieza
from editor.core.modelo.proyecto import Proyecto
from editor.core.modelo.texto import ContenidoTexto
from editor.core.tiempo.nomenclatura import normalizar_nombre

DURACION_IMAGEN_POR_DEFECTO = 5 * FPS
DURACION_TEXTO_POR_DEFECTO = 3 * FPS


def elemento_desde_pieza(
    proyecto: Proyecto,
    pieza: Pieza,
    capa: Capa,
    inicio: int,
    duracion: int | None = None,
    nombre: str | None = None,
    ajuste: str = ORIGINAL,
    en_global: bool = False,
) -> Elemento:
    horneado = pieza.horneado
    if horneado is None:
        raise ErrorModelo(f"La Pieza {pieza.nombre} todavía no está horneada.")
    if capa.tipo is TipoCapa.TEXTO:
        raise ErrorModelo("Una Pieza no puede ir en una capa de texto.")
    es_audio = capa.tipo is TipoCapa.AUDIO
    if es_audio and not horneado.tiene_audio:
        raise ErrorModelo(f"La Pieza {pieza.nombre} no tiene audio.")
    duracion = duracion or horneado.fotogramas_utiles
    return Elemento(
        id=proyecto.nuevo_id(),
        nombre=normalizar_nombre(nombre or pieza.nombre),
        capa=capa,
        tiempo=TiempoElemento(
            inicio=inicio,
            duracion=duracion,
            fuente_entrada=horneado.asas_inicio,
            fuente_duracion=horneado.fotogramas,
        ),
        fuente=ReferenciaFuente(TipoFuente.PIEZA, pieza.id, horneado.version),
        extension="wav" if es_audio else horneado.extension,
        ancho=0 if es_audio else horneado.ancho,
        alto=0 if es_audio else horneado.alto,
        tiene_alfa=False if es_audio else horneado.tiene_alfa,
        tiene_audio=horneado.tiene_audio,
        espacio=Transform() if es_audio else transform_inicial(
            horneado.ancho, horneado.alto, LIENZO.ancho, LIENZO.alto, ajuste
        ),
        en_global=en_global,
    )


def elemento_desde_bruto(
    proyecto: Proyecto,
    bruto: Bruto,
    capa: Capa,
    inicio: int,
    duracion: int | None = None,
    nombre: str | None = None,
    ajuste: str = ORIGINAL,
    en_global: bool = False,
) -> Elemento:
    """Imagen o audio colocados directamente (sin pasar por una Pieza).

    Al materializarse se normalizan: imágenes a PNG y audio a WAV 48 kHz.
    Para un Bruto de audio, `fotogramas_nativos` se mide a 24 fps (E9).
    """
    if bruto.tipo is TipoMedio.VIDEO:
        raise ErrorModelo("Un video se coloca a través de una Pieza del Taller.")
    if bruto.tipo is TipoMedio.IMAGEN:
        if capa.tipo is not TipoCapa.VIDEO:
            raise ErrorModelo("Una imagen va en una capa V.")
        return Elemento(
            id=proyecto.nuevo_id(),
            nombre=normalizar_nombre(nombre or bruto.nombre),
            capa=capa,
            tiempo=TiempoElemento(inicio=inicio, duracion=duracion or DURACION_IMAGEN_POR_DEFECTO, fuente_entrada=0),
            fuente=ReferenciaFuente(TipoFuente.BRUTO, bruto.id),
            extension="png",
            ancho=bruto.ancho,
            alto=bruto.alto,
            tiene_alfa=bruto.tiene_alfa,
            espacio=transform_inicial(bruto.ancho, bruto.alto, LIENZO.ancho, LIENZO.alto, ajuste),
            en_global=en_global,
        )
    if capa.tipo is not TipoCapa.AUDIO:
        raise ErrorModelo("Un audio va en una capa A.")
    disponible = bruto.fotogramas_nativos
    return Elemento(
        id=proyecto.nuevo_id(),
        nombre=normalizar_nombre(nombre or bruto.nombre),
        capa=capa,
        tiempo=TiempoElemento(
            inicio=inicio,
            duracion=duracion or disponible or DURACION_IMAGEN_POR_DEFECTO,
            fuente_entrada=0,
            fuente_duracion=disponible,
        ),
        fuente=ReferenciaFuente(TipoFuente.BRUTO, bruto.id),
        extension="wav",
        tiene_audio=True,
        en_global=en_global,
    )


def elemento_texto(
    proyecto: Proyecto,
    capa: Capa,
    inicio: int,
    texto: str,
    duracion: int = DURACION_TEXTO_POR_DEFECTO,
    nombre: str | None = None,
    en_global: bool = False,
) -> Elemento:
    if capa.tipo is not TipoCapa.TEXTO:
        raise ErrorModelo("Un texto va en una capa T.")
    return Elemento(
        id=proyecto.nuevo_id(),
        nombre=normalizar_nombre(nombre or texto or "texto"),
        capa=capa,
        tiempo=TiempoElemento(inicio=inicio, duracion=duracion, fuente_entrada=0),
        fuente=ReferenciaFuente(TipoFuente.TEXTO),
        texto=ContenidoTexto(texto=texto),
        espacio=Transform(x=LIENZO.ancho / 2, y=LIENZO.alto * 0.8),
        en_global=en_global,
    )
