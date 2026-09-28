"""Pieza: material preparado en el Taller y horneado a 24 fps (tier T1).

La receta de una Pieza es una secuencia de tramos de Brutos, recortados en
**fotogramas nativos** de cada fuente, más una transformación, efectos y el
método de conversión a 24 fps. Al hornearla se produce
un archivo normalizado con 1 s de asas a cada lado.

En esta etapa la mini-timeline de la Pieza es lineal (tramos uno tras otro);
las capas dentro de una Pieza quedan para una ampliación posterior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Mapping

from editor.core.espacio.transform import Transform
from editor.core.estandar import ASAS_FOTOGRAMAS
from editor.core.modelo.bruto import Bruto
from editor.core.modelo.efecto import Efecto
from editor.core.modelo.errores import ErrorModelo, NoEncontrado
from editor.core.tiempo.granularidad import fotogramas_24_de_tramo
from editor.core.tiempo.nomenclatura import NombrePieza


class MetodoConversionFps(Enum):
    TIEMPO = "tiempo"                # conserva la duración: descarta o duplica fotogramas
    CONFORMAR = "conformar"          # cada fotograma nativo es un fotograma de 24 fps
    CAMARA_LENTA = "camara_lenta"    # conformar aplicado a fuentes rápidas
    MEZCLA = "mezcla"                # fusiona fotogramas vecinos
    INTERPOLACION = "interpolacion"  # genera fotogramas intermedios por flujo óptico

    @property
    def conserva_tiempo(self) -> bool:
        return self in (MetodoConversionFps.TIEMPO, MetodoConversionFps.MEZCLA, MetodoConversionFps.INTERPOLACION)


class AudioConformado(Enum):
    """Qué hacer con el audio cuando el método cambia la duración."""

    ESTIRAR_CON_TONO = "estirar_con_tono"   # remuestrear: el tono cambia con la duración
    CONSERVAR_TONO = "conservar_tono"       # WSOLA: misma altura, otra duración
    SILENCIAR = "silenciar"


@dataclass(frozen=True)
class TramoFuente:
    id_bruto: str
    entrada: int   # fotograma nativo (incluido)
    salida: int    # fotograma nativo (excluido)

    def __post_init__(self) -> None:
        if self.entrada < 0 or self.salida <= self.entrada:
            raise ErrorModelo(f"Tramo inválido: [{self.entrada}, {self.salida}).")

    @property
    def fotogramas_nativos(self) -> int:
        return self.salida - self.entrada


@dataclass
class Horneado:
    """Resultado del último horneado de la Pieza."""

    version: int
    extension: str
    ancho: int
    alto: int
    fotogramas: int                 # total del archivo, asas incluidas
    asas_inicio: int = ASAS_FOTOGRAMAS
    asas_fin: int = ASAS_FOTOGRAMAS
    tiene_alfa: bool = False
    tiene_audio: bool = False
    archivo: Path | None = None     # la asigna proyecto_fs

    @property
    def fotogramas_utiles(self) -> int:
        """Fotogramas del tramo elegido, sin asas."""
        return self.fotogramas - self.asas_inicio - self.asas_fin


@dataclass
class Pieza:
    id: str
    numero: int
    nombre: str
    tramos: list[TramoFuente] = field(default_factory=list)
    metodo_fps: MetodoConversionFps = MetodoConversionFps.TIEMPO
    audio_conformado: AudioConformado = AudioConformado.ESTIRAR_CON_TONO
    espacio: Transform = field(default_factory=Transform)
    efectos: list[Efecto] = field(default_factory=list)
    horneado: Horneado | None = None
    # La receta cambió después del último horneado.
    receta_modificada: bool = True

    @property
    def version(self) -> int:
        return 0 if self.horneado is None else self.horneado.version

    @property
    def siguiente_version(self) -> int:
        return self.version + 1

    @property
    def horneada_al_dia(self) -> bool:
        return self.horneado is not None and not self.receta_modificada

    def ids_brutos(self) -> set[str]:
        return {tramo.id_bruto for tramo in self.tramos}

    def fotogramas_24(self, brutos: Mapping[str, Bruto]) -> int:
        """Duración útil de la Pieza a 24 fps, sin asas."""
        total = 0
        for tramo in self.tramos:
            bruto = brutos.get(tramo.id_bruto)
            if bruto is None:
                raise NoEncontrado(f"La Pieza {self.id} usa el Bruto {tramo.id_bruto}, que no existe.")
            fps = bruto.fps
            if fps is None:
                raise ErrorModelo(f"El Bruto {bruto.id} no tiene fps; hay que analizarlo o interpretarlo.")
            total += fotogramas_24_de_tramo(tramo.fotogramas_nativos, Fraction(fps), self.metodo_fps.conserva_tiempo)
        return total

    def nombre_archivo(self) -> NombrePieza:
        return NombrePieza(self.numero, self.nombre, self.id)
