"""Último estado conocido del disco (T5.8).

Lo que el programa leyó al abrir o escribió al guardar. El reconciliador lo
compara con el modelo para saber qué mover, escribir o enviar a la papelera, y
con el disco actual para detectar cambios hechos fuera del programa.

Rutas relativas a la raíz del proyecto, en formato POSIX.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from editor.core.proyecto_fs.manifiestos import Copia


@dataclass(frozen=True)
class Firma:
    """Tamaño y fecha de modificación: basta para notar cambios externos."""

    tamano: int
    modificado_ns: int

    @classmethod
    def de(cls, ruta: Path) -> "Firma | None":
        try:
            info = os.stat(ruta)
        except FileNotFoundError:
            return None
        return cls(info.st_size, info.st_mtime_ns)


@dataclass
class RegistroElemento:
    contenido: str | None        # None para textos o si nunca se materializó
    gemelo: str
    firma_contenido: Firma | None
    firma_gemelo: Firma | None
    huella_gemelo: str
    ref_fuente: str = ""
    version_fuente: int = 0
    extension: str = ""


@dataclass
class RegistroArchivo:
    """Archivo de control o receta: ruta, firma y huella de su contenido."""

    ruta: str
    firma: Firma | None
    huella: str


@dataclass
class EstadoCapitulo:
    elementos: dict[str, RegistroElemento] = field(default_factory=dict)
    shorts: dict[str, RegistroArchivo] = field(default_factory=dict)
    # Manifiestos y guiones del capítulo: ruta relativa → registro.
    control: dict[str, RegistroArchivo] = field(default_factory=dict)


@dataclass
class EstadoDisco:
    raiz: Path
    capitulos: dict[int, EstadoCapitulo] = field(default_factory=dict)
    proyecto: RegistroArchivo | None = None
    piezas: dict[str, RegistroArchivo] = field(default_factory=dict)
    # `_horneado.json` de cada Pieza (estado automático).
    horneados: dict[str, RegistroArchivo] = field(default_factory=dict)
    # Copias conocidas de cada Pieza (de `_pieza.json`), también en capítulos no cargados.
    copias_piezas: dict[str, list[Copia]] = field(default_factory=dict)
    # IDs ya vistos al cargar, para detectar duplicados.
    ids_vistos: set[str] = field(default_factory=set)
    # Archivo de cada Bruto (ID → ruta relativa), para enviarlo a la papelera si se quita.
    brutos: dict[str, str] = field(default_factory=dict)

    def capitulo(self, numero: int) -> EstadoCapitulo:
        return self.capitulos.setdefault(numero, EstadoCapitulo())

    def absoluta(self, relativa: str) -> Path:
        return self.raiz / relativa

    def firma(self, relativa: str) -> Firma | None:
        return Firma.de(self.absoluta(relativa))
