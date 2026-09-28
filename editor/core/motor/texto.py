"""Dibujo de textos con Pillow (T7.5).

El texto se dibuja al tamaño del destino (nítido en vista previa, Shorts o
4K) y se devuelve en RGBA no premultiplicado. Su tamaño natural en el lienzo
es el de la imagen dividido por la escala.

Animaciones de entrada y salida (PROJECT.md, E19): fundido, deslizar arriba o
abajo, escribir (letra a letra) y escala.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from editor.core.modelo.texto import CENTRO, DERECHA, ContenidoTexto, EstiloTexto

registro = logging.getLogger(__name__)

FUENTES_SISTEMA = ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf", "Arial.ttf")


def _color(texto: str) -> tuple[int, int, int, int]:
    texto = texto.lstrip("#")
    if len(texto) == 6:
        texto += "ff"
    return tuple(int(texto[i:i + 2], 16) for i in (0, 2, 4, 6))  # type: ignore[return-value]


@lru_cache(maxsize=64)
def _fuente(nombre: str, tamano: int, carpeta: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidatos = []
    if nombre and carpeta:
        candidatos.append(str(Path(carpeta) / nombre))
    if nombre:
        candidatos.append(nombre)
    candidatos.extend(FUENTES_SISTEMA)
    for candidato in candidatos:
        try:
            return ImageFont.truetype(candidato, tamano)
        except OSError:
            continue
    registro.warning("No se encontró la fuente %r; se usa la de Pillow.", nombre)
    return ImageFont.load_default(tamano)


def _partir(texto: str, fuente, ancho_maximo: float) -> list[str]:
    lineas: list[str] = []
    for parrafo in texto.split("\n"):
        if ancho_maximo <= 0:
            lineas.append(parrafo)
            continue
        actual = ""
        for palabra in parrafo.split(" "):
            prueba = f"{actual} {palabra}".strip()
            if actual and fuente.getlength(prueba) > ancho_maximo:
                lineas.append(actual)
                actual = palabra
            else:
                actual = prueba
        lineas.append(actual)
    return lineas


@lru_cache(maxsize=256)
def _dibujar(texto: str, estilo: EstiloTexto, escala: float, carpeta: str) -> np.ndarray:
    tamano = max(1, round(estilo.tamano * escala))
    fuente = _fuente(estilo.fuente, tamano, carpeta)
    contorno = max(0, round(estilo.contorno_ancho * escala))
    lineas = _partir(texto, fuente, estilo.ancho_maximo * escala) or [""]
    alto_linea = round(tamano * estilo.interlineado)
    anchos = [fuente.getlength(linea) for linea in lineas]
    ancho = max(1, round(max(anchos) + 2 * contorno))
    alto = max(1, alto_linea * (len(lineas) - 1) + tamano + 2 * contorno + round(tamano * 0.3))

    margen = 0
    sombra = estilo.sombra
    if sombra is not None:
        margen = round((abs(sombra.desplazamiento_x) + abs(sombra.desplazamiento_y) + sombra.desenfoque * 2) * escala)
    lienzo = Image.new("RGBA", (ancho + 2 * margen, alto + 2 * margen), (0, 0, 0, 0))

    def escribir(capa: Image.Image, color, desplazamiento=(0, 0), trazo=0, color_trazo=None) -> None:
        dibujo = ImageDraw.Draw(capa)
        for i, linea in enumerate(lineas):
            x = contorno
            if estilo.alineacion == CENTRO:
                x = (ancho - anchos[i]) / 2
            elif estilo.alineacion == DERECHA:
                x = ancho - anchos[i] - contorno
            dibujo.text(
                (margen + x + desplazamiento[0], margen + contorno + i * alto_linea + desplazamiento[1]),
                linea, font=fuente, fill=color, stroke_width=trazo, stroke_fill=color_trazo,
            )

    if sombra is not None:
        capa_sombra = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
        escribir(capa_sombra, _color(sombra.color),
                 (sombra.desplazamiento_x * escala, sombra.desplazamiento_y * escala), contorno, _color(sombra.color))
        if sombra.desenfoque > 0:
            capa_sombra = capa_sombra.filter(ImageFilter.GaussianBlur(sombra.desenfoque * escala))
        lienzo = Image.alpha_composite(lienzo, capa_sombra)
    capa_texto = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    escribir(capa_texto, _color(estilo.color), (0, 0), contorno, _color(estilo.contorno_color) if contorno else None)
    lienzo = Image.alpha_composite(lienzo, capa_texto)
    return np.asarray(lienzo, dtype=np.uint8)


def dibujar(contenido: ContenidoTexto, escala: float, carpeta_fuentes: Path | None = None,
            caracteres: int | None = None) -> np.ndarray:
    """Imagen RGBA del texto a esa escala (píxeles de destino por píxel de lienzo)."""
    texto = contenido.texto if caracteres is None else contenido.texto[:max(0, caracteres)]
    return _dibujar(texto, contenido.estilo, round(escala, 4), str(carpeta_fuentes or ""))


@dataclass(frozen=True)
class EstadoAnimacion:
    opacidad: float = 1.0
    desplazamiento_y: float = 0.0   # px del lienzo
    escala: float = 1.0
    caracteres: int | None = None


def animacion(contenido: ContenidoTexto, f_local: float, duracion: int) -> EstadoAnimacion:
    """Estado de las animaciones de entrada y salida en un fotograma local."""
    largo = max(1, contenido.duracion_animacion)
    opacidad, dy, escala, caracteres = 1.0, 0.0, 1.0, None
    for tipo, avance in (
        (contenido.animacion_entrada, f_local / largo),
        (contenido.animacion_salida, (duracion - f_local) / largo),
    ):
        if tipo == "ninguna" or avance >= 1:
            continue
        avance = max(0.0, avance)
        if tipo == "fundido":
            opacidad *= avance
        elif tipo == "deslizar-arriba":
            dy += (1 - avance) * 40
            opacidad *= avance
        elif tipo == "deslizar-abajo":
            dy -= (1 - avance) * 40
            opacidad *= avance
        elif tipo == "escala":
            escala *= 0.6 + 0.4 * avance
            opacidad *= avance
        elif tipo == "escribir":
            caracteres = int(len(contenido.texto) * avance)
    return EstadoAnimacion(opacidad, dy, escala, caracteres)
