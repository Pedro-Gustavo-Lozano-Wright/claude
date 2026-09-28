"""Interfaz común de las fuentes de imagen.

Una fuente entrega fotogramas RGBA **no premultiplicados** en `uint8`, con forma
(alto, ancho, 4). El compositor los premultiplica al mezclar. Cualquier motor
(PyAV hoy, MLT u otro mañana) o el banco de vista previa implementan esta
misma interfaz, así el compositor no sabe de dónde vienen los píxeles.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

Imagen = np.ndarray  # (alto, ancho, 4) uint8 RGBA


@dataclass(frozen=True)
class InfoFuente:
    ancho: int
    alto: int
    fps: Fraction | None        # None para imágenes fijas
    fotogramas: int             # 1 para imágenes fijas
    tiene_alfa: bool
    tiene_audio: bool

    @property
    def es_fija(self) -> bool:
        return self.fps is None


class FuenteImagen(ABC):
    info: InfoFuente

    @abstractmethod
    def fotograma(self, n: int, tamano: tuple[int, int] | None = None) -> Imagen:
        """Fotograma n (se limita al rango válido) escalado a `tamano` (ancho, alto) si se pide."""

    def cerrar(self) -> None:
        """Libera recursos (archivos abiertos)."""


class ErrorFuente(RuntimeError):
    """No se pudo abrir o leer una fuente."""


def transparente(ancho: int, alto: int) -> Imagen:
    return np.zeros((max(1, alto), max(1, ancho), 4), dtype=np.uint8)
