"""Conversión de fotogramas nativos a 24 fps.

Entrada: los fotogramas del tramo en orden, cada uno con su instante en
segundos. Salida: los fotogramas a 24 fps según el método:

- tiempo: para cada instante de salida, el fotograma nativo vigente (descarta o duplica).
- conformar / cámara lenta: cada fotograma nativo es uno de salida (la duración cambia).
- mezcla: promedio ponderado de los dos vecinos.
- interpolación: flujo óptico (OpenCV DIS) y deformación de ambos vecinos al instante intermedio.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Iterable, Iterator

import cv2
import numpy as np

from editor.core.estandar import FPS
from editor.core.modelo.pieza import MetodoConversionFps

Cuadro = tuple[float, np.ndarray]  # (segundos desde el inicio del tramo, RGBA uint8)


def convertir(cuadros: Iterable[Cuadro], metodo: MetodoConversionFps, duracion_segundos: float) -> Iterator[np.ndarray]:
    if metodo in (MetodoConversionFps.CONFORMAR, MetodoConversionFps.CAMARA_LENTA):
        for _, imagen in cuadros:
            yield imagen
        return
    salida = 0
    total = max(1, round(duracion_segundos * FPS))
    anterior: Cuadro | None = None
    flujo = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST) if metodo is MetodoConversionFps.INTERPOLACION else None
    for actual in cuadros:
        if anterior is None:
            anterior = actual
            continue
        while salida < total and salida / FPS < actual[0]:
            yield _entre(anterior, actual, salida / FPS, metodo, flujo)
            salida += 1
        anterior = actual
    while anterior is not None and salida < total:
        yield anterior[1]
        salida += 1


def _entre(a: Cuadro, b: Cuadro, t: float, metodo: MetodoConversionFps, flujo) -> np.ndarray:
    if metodo is MetodoConversionFps.TIEMPO or b[0] <= a[0]:
        return a[1]
    peso = (t - a[0]) / (b[0] - a[0])
    if metodo is MetodoConversionFps.MEZCLA or flujo is None:
        return (a[1].astype(np.float32) * (1 - peso) + b[1].astype(np.float32) * peso + 0.5).astype(np.uint8)
    gris_a = cv2.cvtColor(a[1], cv2.COLOR_RGBA2GRAY)
    gris_b = cv2.cvtColor(b[1], cv2.COLOR_RGBA2GRAY)
    campo = flujo.calc(gris_a, gris_b, None)
    alto, ancho = gris_a.shape
    rejilla = np.dstack(np.meshgrid(np.arange(ancho), np.arange(alto))).astype(np.float32)
    desde_a = cv2.remap(a[1], rejilla - campo * peso, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    desde_b = cv2.remap(b[1], rejilla + campo * (1 - peso), None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return (desde_a.astype(np.float32) * (1 - peso) + desde_b.astype(np.float32) * peso + 0.5).astype(np.uint8)


def fotogramas_salida(fotogramas_nativos: int, fps: Fraction, metodo: MetodoConversionFps) -> int:
    if not metodo.conserva_tiempo:
        return fotogramas_nativos
    return max(1, round(Fraction(fotogramas_nativos) / fps * FPS))


def factor_audio(fps: Fraction, metodo: MetodoConversionFps) -> float:
    """Cuánto se estira el audio: 1.0 si se conserva el tiempo; 24/fps si se conforma."""
    return 1.0 if metodo.conserva_tiempo else float(fps / FPS)
