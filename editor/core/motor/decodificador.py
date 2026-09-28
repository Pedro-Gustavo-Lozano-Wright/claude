"""Decodificación con PyAV (video, alfa incluido) y Pillow (imágenes).

- Búsqueda **exacta por fotograma**: se salta al fotograma clave anterior y se
  decodifica hasta el pedido. Si se pide el siguiente de lo ya decodificado, se
  sigue sin saltar (reproducción secuencial barata).
- Escalado con swscale al tamaño que pide el compositor (no se decodifica 4K
  para una vista previa de 256×144 sin reducir antes).
- `GestorFuentes` reutiliza contenedores abiertos (LRU) y los protege con un
  candado cada uno: un contenedor de PyAV no se debe usar desde dos hilos.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image

from editor.core.motor.cache_fotogramas import CacheFotogramas
from editor.core.motor.motor_base import ErrorFuente, FuenteImagen, Imagen, InfoFuente

EXTENSIONES_IMAGEN = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"}
FORMATOS_CON_ALFA = ("yuva", "rgba", "bgra", "argb", "abgr", "ya", "gbrap", "pal8")
SALTO_SECUENCIAL = 48  # hasta 2 s por delante se decodifica en vez de saltar


def tiene_alfa(formato_pixel: str | None) -> bool:
    return bool(formato_pixel) and formato_pixel.startswith(FORMATOS_CON_ALFA)


class FuenteVideo(FuenteImagen):
    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        try:
            self._contenedor = av.open(str(ruta))
        except (av.error.FFmpegError, OSError) as error:
            raise ErrorFuente(f"No se pudo abrir {ruta}: {error}") from error
        if not self._contenedor.streams.video:
            self._contenedor.close()
            raise ErrorFuente(f"{ruta} no tiene video.")
        self._stream = self._contenedor.streams.video[0]
        self._stream.thread_type = "AUTO"
        fps = self._stream.average_rate or self._stream.guessed_rate or Fraction(24)
        self._fps = Fraction(fps)
        self._base = self._stream.time_base or Fraction(1, 1000)
        self._inicio = self._stream.start_time or 0
        fotogramas = self._stream.frames
        if not fotogramas and self._stream.duration:
            fotogramas = int(self._stream.duration * self._base * self._fps)
        if not fotogramas and self._contenedor.duration:
            fotogramas = int(self._contenedor.duration / av.time_base * self._fps)
        codec = self._stream.codec_context
        self.info = InfoFuente(
            ancho=codec.width,
            alto=codec.height,
            fps=self._fps,
            fotogramas=max(1, int(fotogramas or 1)),
            tiene_alfa=tiene_alfa(codec.pix_fmt),
            tiene_audio=bool(self._contenedor.streams.audio),
        )
        self._decodificador = None
        self._ultimo_indice = -1
        self._ultimo: av.VideoFrame | None = None

    def _indice_de(self, cuadro: av.VideoFrame) -> int:
        pts = cuadro.pts if cuadro.pts is not None else 0
        return round((pts - self._inicio) * self._base * self._fps)

    def _saltar(self, n: int) -> None:
        objetivo = int(Fraction(n) / self._fps / self._base) + self._inicio
        self._contenedor.seek(max(objetivo, self._inicio), stream=self._stream, backward=True, any_frame=False)
        self._decodificador = self._contenedor.decode(self._stream)
        self._ultimo_indice = -1
        self._ultimo = None

    def _cuadro(self, n: int) -> av.VideoFrame:
        n = max(0, min(n, self.info.fotogramas - 1))
        if self._ultimo is not None and self._ultimo_indice == n:
            return self._ultimo
        if self._decodificador is None or not (self._ultimo_indice < n <= self._ultimo_indice + SALTO_SECUENCIAL):
            self._saltar(n)
        assert self._decodificador is not None
        for cuadro in self._decodificador:
            indice = self._indice_de(cuadro)
            self._ultimo, self._ultimo_indice = cuadro, indice
            if indice >= n:
                return cuadro
        if self._ultimo is None:
            raise ErrorFuente(f"No se pudo decodificar el fotograma {n} de {self.ruta}")
        return self._ultimo  # fin del archivo: se repite el último

    def fotograma(self, n: int, tamano: tuple[int, int] | None = None) -> Imagen:
        cuadro = self._cuadro(n)
        ancho, alto = tamano or (self.info.ancho, self.info.alto)
        return cuadro.reformat(width=max(1, ancho), height=max(1, alto), format="rgba").to_ndarray()

    def cerrar(self) -> None:
        self._contenedor.close()


class FuenteImagenFija(FuenteImagen):
    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        try:
            with Image.open(ruta) as imagen:
                self._original = imagen.convert("RGBA")
                modo = imagen.mode
        except OSError as error:
            raise ErrorFuente(f"No se pudo abrir {ruta}: {error}") from error
        self.info = InfoFuente(
            ancho=self._original.width,
            alto=self._original.height,
            fps=None,
            fotogramas=1,
            tiene_alfa="A" in modo or "transparency" in self._original.info,
            tiene_audio=False,
        )
        self._escaladas: dict[tuple[int, int], Imagen] = {}

    def fotograma(self, n: int, tamano: tuple[int, int] | None = None) -> Imagen:
        clave = tamano or (self.info.ancho, self.info.alto)
        if clave not in self._escaladas:
            imagen = self._original if clave == self._original.size else self._original.resize(
                (max(1, clave[0]), max(1, clave[1])), Image.Resampling.LANCZOS
            )
            self._escaladas = {clave: np.asarray(imagen, dtype=np.uint8).copy()}
        return self._escaladas[clave]


def abrir(ruta: Path) -> FuenteImagen:
    if ruta.suffix.lower().lstrip(".") in EXTENSIONES_IMAGEN:
        return FuenteImagenFija(ruta)
    return FuenteVideo(ruta)


class _Entrada:
    def __init__(self, fuente: FuenteImagen, modificado: int) -> None:
        self.fuente = fuente
        self.modificado = modificado
        self.candado = threading.Lock()


def _modificado(ruta: Path) -> int:
    try:
        return ruta.stat().st_mtime_ns
    except FileNotFoundError:
        raise ErrorFuente(f"No existe {ruta}") from None


class GestorFuentes:
    """Fuentes abiertas reutilizables + caché de fotogramas."""

    def __init__(self, cache: CacheFotogramas | None = None, maximo_abiertas: int = 16) -> None:
        self.cache = cache or CacheFotogramas()
        self.maximo = maximo_abiertas
        self._abiertas: OrderedDict[Path, _Entrada] = OrderedDict()
        self._candado = threading.Lock()

    def _entrada(self, ruta: Path) -> _Entrada:
        modificado = _modificado(ruta)
        with self._candado:
            entrada = self._abiertas.get(ruta)
            if entrada is not None and entrada.modificado != modificado:
                # El archivo se reemplazó (rehorneado, rematerializado): se reabre.
                self._abiertas.pop(ruta)
                with entrada.candado:
                    entrada.fuente.cerrar()
                self.cache.olvidar(ruta)
                entrada = None
            if entrada is None:
                entrada = _Entrada(abrir(ruta), modificado)
                self._abiertas[ruta] = entrada
                while len(self._abiertas) > self.maximo:
                    _, vieja = self._abiertas.popitem(last=False)
                    with vieja.candado:
                        vieja.fuente.cerrar()
            else:
                self._abiertas.move_to_end(ruta)
            return entrada

    def info(self, ruta: Path) -> InfoFuente:
        return self._entrada(ruta).fuente.info

    def fotograma(self, ruta: Path, n: int, tamano: tuple[int, int] | None = None) -> Imagen:
        entrada = self._entrada(ruta)
        if entrada.fuente.info.es_fija:
            n = 0
        clave = (ruta, n, tamano)
        guardado = self.cache.obtener(clave)
        if guardado is not None:
            return guardado
        with entrada.candado:
            imagen = entrada.fuente.fotograma(n, tamano)
        self.cache.guardar(clave, imagen)
        return imagen

    def cerrar(self, ruta: Path | None = None) -> None:
        """Cierra una fuente (antes de renombrarla o reemplazarla) o todas."""
        with self._candado:
            rutas = [ruta] if ruta is not None else list(self._abiertas)
            for actual in rutas:
                entrada = self._abiertas.pop(actual, None)
                if entrada is not None:
                    with entrada.candado:
                        entrada.fuente.cerrar()
                self.cache.olvidar(actual)
