"""Banco de fotogramas de vista previa, nivel 0.

Cada archivo de video (horneado de Pieza o su copia) tiene un banco en
`.cache/banco/<clave>/`: imágenes de 256×144 a 10 fps (JPEG, o WebP si hay
alfa) y un `_indice.json`. La clave sale del tamaño y la fecha del archivo:
las copias materializadas (que conservan la fecha) comparten el banco de su
Pieza, y un archivo reemplazado genera un banco nuevo.

`GestorFuentesBanco` es un `GestorFuentes` que lee del banco en vez de
decodificar: el compositor funciona igual, solo más rápido y en pequeño.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

from editor.core.estandar import ParametrosBanco
from editor.core.motor.decodificador import EXTENSIONES_IMAGEN, FuenteVideo, GestorFuentes, _Entrada, _modificado
from editor.core.motor.motor_base import ErrorFuente, FuenteImagen, Imagen, InfoFuente
from editor.core.tareas.cola import Contexto
from editor.core.tiempo.nomenclatura import CARPETA_CACHE

INDICE = "_indice.json"


def clave(ruta: Path) -> str:
    info = ruta.stat()
    return f"{info.st_size:x}_{info.st_mtime_ns:x}"


def carpeta_banco(raiz: Path, ruta: Path) -> Path:
    return raiz / CARPETA_CACHE / "banco" / clave(ruta)


def existe(raiz: Path, ruta: Path) -> bool:
    return (carpeta_banco(raiz, ruta) / INDICE).exists()


def generar(raiz: Path, ruta: Path, parametros: ParametrosBanco, contexto: Contexto) -> Path:
    """Tarea de fondo: crea el banco de un archivo de video (si no existe ya)."""
    carpeta = carpeta_banco(raiz, ruta)
    if (carpeta / INDICE).exists():
        return carpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    fuente = FuenteVideo(ruta)
    try:
        info = fuente.info
        fps = info.fps or Fraction(24)
        total = max(1, int(info.fotogramas / fps * parametros.fps))
        escala = min(parametros.ancho / info.ancho, parametros.alto / info.alto)
        tamano = (max(1, round(info.ancho * escala)), max(1, round(info.alto * escala)))
        formato = parametros.formato_alfa if info.tiene_alfa else parametros.formato_opaco
        for k in range(total):
            n = min(info.fotogramas - 1, round(k / parametros.fps * fps))
            imagen = Image.fromarray(fuente.fotograma(n, tamano))
            if formato == "jpg":
                imagen = imagen.convert("RGB")
            imagen.save(carpeta / f"f{k:06d}.{formato}", quality=parametros.calidad_jpeg)
            if k % 10 == 0:
                contexto.progreso(k / total, f"Banco de {ruta.name}")
    finally:
        fuente.cerrar()
    (carpeta / INDICE).write_text(json.dumps({
        "fps_banco": parametros.fps,
        "fps_fuente": str(fps),
        "fotogramas": total,
        "fotogramas_fuente": info.fotogramas,
        "ancho": info.ancho,
        "alto": info.alto,
        "alfa": info.tiene_alfa,
        "formato": formato,
    }), encoding="utf-8")
    contexto.progreso(1.0, f"Banco de {ruta.name} listo")
    return carpeta


class FuenteBanco(FuenteImagen):
    def __init__(self, carpeta: Path) -> None:
        self.carpeta = carpeta
        datos = json.loads((carpeta / INDICE).read_text(encoding="utf-8"))
        self._fps_banco = int(datos["fps_banco"])
        self._fps_fuente = Fraction(datos["fps_fuente"])
        self._total = int(datos["fotogramas"])
        self._formato = datos["formato"]
        # Tamaño natural = el del archivo original: la geometría no cambia al usar el banco.
        self.info = InfoFuente(
            ancho=int(datos["ancho"]), alto=int(datos["alto"]), fps=self._fps_fuente,
            fotogramas=int(datos["fotogramas_fuente"]), tiene_alfa=bool(datos["alfa"]), tiene_audio=False,
        )

    def fotograma(self, n: int, tamano: tuple[int, int] | None = None) -> Imagen:
        k = max(0, min(self._total - 1, round(n / self._fps_fuente * self._fps_banco)))
        with Image.open(self.carpeta / f"f{k:06d}.{self._formato}") as imagen:
            imagen = imagen.convert("RGBA")
            if tamano is not None and imagen.size != tamano:
                imagen = imagen.resize((max(1, tamano[0]), max(1, tamano[1])), Image.Resampling.BILINEAR)
            return np.asarray(imagen, dtype=np.uint8).copy()


class GestorFuentesBanco(GestorFuentes):
    """Lee del banco cuando existe; si no, decodifica el archivo (más lento, pero correcto)."""

    def __init__(self, raiz: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.raiz = raiz

    def _entrada(self, ruta: Path) -> _Entrada:
        if ruta.suffix.lower().lstrip(".") in EXTENSIONES_IMAGEN:
            return super()._entrada(ruta)
        carpeta = carpeta_banco(self.raiz, ruta)
        if not (carpeta / INDICE).exists():
            return super()._entrada(ruta)
        with self._candado:
            entrada = self._abiertas.get(carpeta)
            if entrada is None:
                try:
                    entrada = _Entrada(FuenteBanco(carpeta), _modificado(carpeta / INDICE))
                except (OSError, ValueError, KeyError) as error:
                    raise ErrorFuente(f"Banco dañado en {carpeta}: {error}") from error
                self._abiertas[carpeta] = entrada
            return entrada
