"""Bruto: archivo original importado a `brutos/`. Nunca se modifica (tier T0).

Guarda lo que se sabe del archivo y la interpretación de fps que eligió el
usuario.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path

from editor.core.tiempo.nomenclatura import NombreBruto


class TipoMedio(Enum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGEN = "imagen"

    @property
    def subcarpeta(self) -> str:
        return self.value


@dataclass
class Bruto:
    id: str
    numero: int
    nombre: str
    tipo: TipoMedio
    extension: str
    # Datos del análisis.
    ancho: int = 0
    alto: int = 0
    fotogramas_nativos: int = 0          # duración en fotogramas de la propia fuente
    fps_detectado: Fraction | None = None
    fps_medido: Fraction | None = None
    vfr: bool = False
    tiene_alfa: bool = False
    tiene_audio: bool = False
    audio_frecuencia: int = 0
    # Decisión del usuario en el Taller.
    fps_interpretado: Fraction | None = None
    origen: str = ""                     # ruta desde la que se importó (informativa)
    archivo: Path | None = None          # ruta en brutos/; la asigna proyecto_fs

    @property
    def fps(self) -> Fraction | None:
        """fps efectivo: el interpretado; si no, el medido; si no, el detectado."""
        return self.fps_interpretado or self.fps_medido or self.fps_detectado

    @property
    def necesita_revision_fps(self) -> bool:
        """El Taller avisa si el fps declarado no coincide con el medido o si es variable."""
        if self.tipo is not TipoMedio.VIDEO:
            return False
        if self.vfr:
            return True
        return (
            self.fps_detectado is not None
            and self.fps_medido is not None
            and self.fps_detectado != self.fps_medido
        )

    @property
    def duracion_segundos(self) -> Fraction | None:
        if self.fps is None or self.fotogramas_nativos <= 0:
            return None
        return Fraction(self.fotogramas_nativos) / self.fps

    def nombre_archivo(self) -> NombreBruto:
        return NombreBruto(self.numero, self.nombre, self.id, self.extension)
