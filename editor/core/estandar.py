"""Estándar HD720-24: el único formato de edición y render del editor.

Las constantes de este módulo son fijas por diseño:
lienzo 1280×720 en 16:9, 24 fps, capítulos de exactamente 24 minutos.
La clase `Estandar` agrupa los parámetros de codificación que sí se pueden
ajustar por proyecto; cada proyecto guarda su propia copia en `_proyecto.json`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from fractions import Fraction
from pathlib import Path
from typing import Any

# --- Tiempo -------------------------------------------------------------------

FPS = 24
FPS_FRACCION = Fraction(FPS, 1)
SEGUNDOS_POR_MINUTO = 60
MINUTOS_POR_CAPITULO = 24
FOTOGRAMAS_POR_SEGUNDO = FPS
FOTOGRAMAS_POR_MINUTO = FPS * SEGUNDOS_POR_MINUTO            # 1440
FOTOGRAMAS_POR_CAPITULO = FOTOGRAMAS_POR_MINUTO * MINUTOS_POR_CAPITULO  # 34 560

CAPITULO_MINIMO = 1
CAPITULO_MAXIMO = 1000

ASAS_SEGUNDOS = 1
ASAS_FOTOGRAMAS = ASAS_SEGUNDOS * FPS                          # 24

# --- Espacio ------------------------------------------------------------------

LIENZO_ANCHO = 1280
LIENZO_ALTO = 720
RELACION_ASPECTO = Fraction(16, 9)

SHORT_ANCHO = 720
SHORT_ALTO = 1280
RELACION_SHORT = Fraction(9, 16)
# Ancho de la ventana vertical sobre el lienzo con zoom 1: 720 × 9/16 = 405 px.
VENTANA_VERTICAL_ANCHO = LIENZO_ALTO * 9 / 16

PIEZA_ANCHO_MAXIMO = 2560
PIEZA_ALTO_MAXIMO = 1440

# --- Capas --------------------------------------------------------------------

CAPAS_POR_TIPO = 9


@dataclass(frozen=True)
class ParametrosRender:
    """Codificación del render final de minutos y capítulos."""

    codec_video: str = "libx264"
    crf: int = 18
    preset: str = "medium"
    formato_pixel: str = "yuv420p"
    codec_audio: str = "aac"
    bitrate_audio: str = "192k"
    contenedor: str = "mp4"
    # "ninguna", "vaapi" o "nvenc"; con "ninguna" se usa codec_video por software.
    aceleracion: str = "ninguna"


@dataclass(frozen=True)
class ParametrosPieza:
    """Codificación de las Piezas horneadas en el Taller."""

    codec_opaco: str = "libx264"
    crf_opaco: int = 14
    contenedor_opaco: str = "mp4"
    codec_alfa: str = "prores_ks"
    perfil_alfa: str = "4444"
    contenedor_alfa: str = "mov"
    ancho_maximo: int = PIEZA_ANCHO_MAXIMO
    alto_maximo: int = PIEZA_ALTO_MAXIMO


@dataclass(frozen=True)
class ParametrosBanco:
    """Banco de fotogramas de la vista previa (nivel 0)."""

    ancho: int = 256
    alto: int = 144
    fps: int = 10
    calidad_jpeg: int = 75
    formato_opaco: str = "jpg"
    formato_alfa: str = "webp"


@dataclass(frozen=True)
class ParametrosPrerender:
    """Vista previa pre-renderizada por minuto (nivel 3)."""

    ancho: int = 960
    alto: int = 540
    codec_video: str = "libx264"
    preset: str = "ultrafast"
    crf: int = 23


@dataclass(frozen=True)
class Estandar:
    """Parámetros de un proyecto.

    Lienzo, fps y duración de capítulo son fijos y se validan al cargar; el
    resto de los valores se pueden ajustar por proyecto.
    """

    lienzo_ancho: int = LIENZO_ANCHO
    lienzo_alto: int = LIENZO_ALTO
    fps: int = FPS
    audio_frecuencia: int = 48_000
    audio_canales: int = 2
    render: ParametrosRender = field(default_factory=ParametrosRender)
    pieza: ParametrosPieza = field(default_factory=ParametrosPieza)
    banco: ParametrosBanco = field(default_factory=ParametrosBanco)
    prerender: ParametrosPrerender = field(default_factory=ParametrosPrerender)

    def __post_init__(self) -> None:
        self.validar()

    def validar(self) -> None:
        if self.fps != FPS:
            raise ValueError(f"El estándar es {FPS} fps; se recibió {self.fps}.")
        if (self.lienzo_ancho, self.lienzo_alto) != (LIENZO_ANCHO, LIENZO_ALTO):
            raise ValueError(
                f"El lienzo es {LIENZO_ANCHO}×{LIENZO_ALTO}; "
                f"se recibió {self.lienzo_ancho}×{self.lienzo_alto}."
            )
        if self.audio_canales not in (1, 2):
            raise ValueError("El audio debe ser mono o estéreo.")

    @property
    def fps_fraccion(self) -> Fraction:
        return Fraction(self.fps, 1)

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "Estandar":
        anidados = {
            "render": ParametrosRender,
            "pieza": ParametrosPieza,
            "banco": ParametrosBanco,
            "prerender": ParametrosPrerender,
        }
        argumentos: dict[str, Any] = {}
        nombres = {f.name for f in fields(cls)}
        for clave, valor in datos.items():
            if clave not in nombres:
                continue
            if clave in anidados and isinstance(valor, dict):
                argumentos[clave] = _construir(anidados[clave], valor)
            else:
                argumentos[clave] = valor
        return cls(**argumentos)

    @classmethod
    def cargar(cls, ruta: Path) -> "Estandar":
        with ruta.open(encoding="utf-8") as archivo:
            return cls.desde_dict(json.load(archivo))

    def guardar(self, ruta: Path) -> None:
        ruta.write_text(
            json.dumps(self.a_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _construir(tipo: type, datos: dict[str, Any]) -> Any:
    nombres = {f.name for f in fields(tipo)}
    return tipo(**{clave: valor for clave, valor in datos.items() if clave in nombres})
