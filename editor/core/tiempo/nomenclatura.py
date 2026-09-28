"""Nomenclatura única de carpetas y archivos.

Convierte en ambos sentidos entre los nombres del disco y los datos que
expresan, y genera los IDs estables del proyecto.

    Elemento  min02_seg12f08_dur05s00_V2_puerta-abre__a3f90e.mov
    Short     min02_seg10f00_dur45s00_momento-clave__b71c4d.json
    Bruto     bru0001_toma-calle__7c2185.mp4
    Pieza     pie0001_puerta-abre__5e1c3a
    Capítulo  cap0001        Minuto  min02
    Render    cap0001_min00_v003.mp4 · cap0001_min05-08_v001.mp4 · cap0001_completo_v002.mp4
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path

from editor.core.estandar import CAPAS_POR_TIPO, CAPITULO_MAXIMO, CAPITULO_MINIMO, MINUTOS_POR_CAPITULO
from editor.core.tiempo.granularidad import Duracion, ErrorTiempo, Instante


class NombreInvalido(ValueError):
    pass


# --- Archivos y carpetas fijos ------------------------------------------------

PREFIJO_CONTROL = "_"
ARCHIVO_PROYECTO = "_proyecto.json"
ARCHIVO_CAPITULO = "_capitulo.json"
ARCHIVO_MINUTO = "_minuto.json"
ARCHIVO_GUION = "_guion.txt"
ARCHIVO_PIEZA = "_pieza.json"
# Estado automático (lo escriben los servicios en el momento, no el guardado del usuario).
ARCHIVO_RENDERS = "_renders.json"
ARCHIVO_HORNEADO = "_horneado.json"

CARPETA_BRUTOS = "brutos"
CARPETA_TALLER = "taller"
CARPETA_RECURSOS = "recursos"
CARPETA_GLOBAL = "global"
CARPETA_RENDER = "render"
CARPETA_SHORTS = "shorts"
CARPETA_DIARIO = ".diario"
CARPETA_AUTOSAVE = ".autosave"
CARPETA_CACHE = ".cache"
CARPETA_PAPELERA = ".papelera"
ARCHIVO_BLOQUEO = ".bloqueo"

# Versión del formato de los archivos de control; permite migrar proyectos viejos.
VERSION_ESQUEMA = 1

SUBCARPETAS_BRUTOS = ("video", "audio", "imagen")
SUBCARPETAS_RECURSOS = ("fuentes", "luts")

EXTENSION_GEMELO = "json"

LONGITUD_NOMBRE_MAXIMA = 32
# 6 hexadecimales = 16,7 millones de IDs: alcanza para 1000 capítulos llenos.
LONGITUD_ID = 6

# --- Expresiones regulares ----------------------------------------------------

_NOMBRE = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_ID = r"[0-9a-f]{6}"
_INICIO = r"min\d{2}_seg\d{2}f\d{2}"
_DURACION = r"dur(?:\d{2}m)?\d{2}s\d{2}"

PATRON_ELEMENTO = re.compile(
    rf"^(?P<inicio>{_INICIO})_(?P<duracion>{_DURACION})_(?P<capa>[VAT][1-9])"
    rf"_(?P<nombre>{_NOMBRE})__(?P<id>{_ID})\.(?P<extension>[a-z0-9]+)$"
)
PATRON_SHORT = re.compile(
    rf"^(?P<inicio>{_INICIO})_(?P<duracion>{_DURACION})"
    rf"_(?P<nombre>{_NOMBRE})__(?P<id>{_ID})(?:_v(?P<version>\d{{3}})(?:_(?P<idioma>[a-z]{{2,3}}))?)?"
    rf"\.(?P<extension>[a-z0-9]+)$"
)
PATRON_BRUTO = re.compile(rf"^bru(?P<numero>\d{{4}})_(?P<nombre>{_NOMBRE})__(?P<id>{_ID})\.(?P<extension>[a-z0-9]+)$")
PATRON_PIEZA = re.compile(rf"^pie(?P<numero>\d{{4}})_(?P<nombre>{_NOMBRE})__(?P<id>{_ID})(?:\.(?P<extension>[a-z0-9]+))?$")
PATRON_CAPITULO = re.compile(r"^cap(?P<numero>\d{4})$")
PATRON_MINUTO = re.compile(r"^min(?P<numero>\d{2})$")
PATRON_RENDER = re.compile(
    r"^cap(?P<capitulo>\d{4})_(?:(?P<completo>completo)|min(?P<desde>\d{2})(?:-(?P<hasta>\d{2}))?)"
    r"_v(?P<version>\d{3})(?:_(?P<idioma>[a-z]{2,3}))?\.(?P<extension>[a-z0-9]+)$"
)
PATRON_ID = re.compile(rf"^{_ID}$")


# --- Nombres descriptivos ------------------------------------------------------

def normalizar_nombre(texto: str) -> str:
    """Texto libre → nombre descriptivo válido: minúsculas, números y guiones, ≤ 32."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")
    limpio = limpio[:LONGITUD_NOMBRE_MAXIMA].rstrip("-")
    return limpio or "sin-nombre"


def es_nombre_valido(nombre: str) -> bool:
    return len(nombre) <= LONGITUD_NOMBRE_MAXIMA and re.fullmatch(_NOMBRE, nombre) is not None


def es_archivo_control(nombre_archivo: str) -> bool:
    return nombre_archivo.startswith(PREFIJO_CONTROL)


def normalizar_extension(extension: str) -> str:
    return extension.lower().lstrip(".")


# --- Capas ---------------------------------------------------------------------

TIPOS_CAPA = ("V", "A", "T")


def validar_codigo_capa(codigo: str) -> tuple[str, int]:
    if len(codigo) != 2 or codigo[0] not in TIPOS_CAPA or not codigo[1].isdigit():
        raise NombreInvalido(f"Capa inválida: {codigo!r}")
    numero = int(codigo[1])
    if not 1 <= numero <= CAPAS_POR_TIPO:
        raise NombreInvalido(f"Número de capa fuera de rango: {codigo!r}")
    return codigo[0], numero


# --- Elementos -----------------------------------------------------------------

@dataclass(frozen=True)
class NombreElemento:
    """Datos que expresa el nombre de archivo de un Elemento."""

    inicio: Instante
    duracion: Duracion
    capa: str
    nombre: str
    id: str
    extension: str

    def __post_init__(self) -> None:
        validar_codigo_capa(self.capa)
        if not es_nombre_valido(self.nombre):
            raise NombreInvalido(f"Nombre descriptivo inválido: {self.nombre!r}")
        if not es_id_valido(self.id):
            raise NombreInvalido(f"ID inválido: {self.id!r}")
        if self.inicio.minuto >= MINUTOS_POR_CAPITULO:
            raise NombreInvalido(f"El Elemento empieza fuera del capítulo: {self.inicio}")

    @property
    def base(self) -> str:
        """Nombre sin extensión; es común al contenido y a su gemelo."""
        return f"{self.inicio.texto()}_{self.duracion.texto()}_{self.capa}_{self.nombre}__{self.id}"

    @property
    def archivo(self) -> str:
        return f"{self.base}.{self.extension}"

    @property
    def gemelo(self) -> str:
        return f"{self.base}.{EXTENSION_GEMELO}"

    @property
    def carpeta_minuto(self) -> str:
        return codigo_minuto(self.inicio.minuto)

    @property
    def es_texto(self) -> bool:
        """Los Elementos T son solo su .json: contenido y gemelo coinciden."""
        return self.capa.startswith("T")

    def con(self, **cambios: object) -> "NombreElemento":
        return replace(self, **cambios)

    @classmethod
    def desde_archivo(cls, nombre_archivo: str) -> "NombreElemento":
        coincidencia = PATRON_ELEMENTO.match(nombre_archivo)
        if coincidencia is None:
            raise NombreInvalido(f"No es un nombre de Elemento: {nombre_archivo!r}")
        try:
            return cls(
                inicio=Instante.desde_texto(coincidencia["inicio"]),
                duracion=Duracion.desde_texto(coincidencia["duracion"]),
                capa=coincidencia["capa"],
                nombre=coincidencia["nombre"],
                id=coincidencia["id"],
                extension=coincidencia["extension"],
            )
        except ErrorTiempo as error:
            raise NombreInvalido(f"{nombre_archivo!r}: {error}") from error

    def __str__(self) -> str:
        return self.archivo


def es_nombre_elemento(nombre_archivo: str) -> bool:
    return PATRON_ELEMENTO.match(nombre_archivo) is not None


# --- Shorts --------------------------------------------------------------------

@dataclass(frozen=True)
class NombreShort:
    """Nombre de un Short: la gramática del Elemento sin capa."""

    inicio: Instante
    duracion: Duracion
    nombre: str
    id: str

    def __post_init__(self) -> None:
        if not es_nombre_valido(self.nombre):
            raise NombreInvalido(f"Nombre descriptivo inválido: {self.nombre!r}")
        if not es_id_valido(self.id):
            raise NombreInvalido(f"ID inválido: {self.id!r}")

    @property
    def base(self) -> str:
        return f"{self.inicio.texto()}_{self.duracion.texto()}_{self.nombre}__{self.id}"

    @property
    def receta(self) -> str:
        return f"{self.base}.{EXTENSION_GEMELO}"

    def render(self, version: int, extension: str = "mp4", idioma: str | None = None) -> str:
        sufijo = f"_{_idioma(idioma)}" if idioma else ""
        return f"{self.base}_v{_version(version)}{sufijo}.{extension}"

    @classmethod
    def desde_archivo(cls, nombre_archivo: str) -> tuple["NombreShort", int | None]:
        """Devuelve el nombre y la versión (None si es la receta)."""
        coincidencia = PATRON_SHORT.match(nombre_archivo)
        if coincidencia is None:
            raise NombreInvalido(f"No es un nombre de Short: {nombre_archivo!r}")
        try:
            nombre = cls(
                inicio=Instante.desde_texto(coincidencia["inicio"]),
                duracion=Duracion.desde_texto(coincidencia["duracion"]),
                nombre=coincidencia["nombre"],
                id=coincidencia["id"],
            )
        except ErrorTiempo as error:
            raise NombreInvalido(f"{nombre_archivo!r}: {error}") from error
        version = coincidencia["version"]
        return nombre, int(version) if version is not None else None


# --- Brutos y Piezas -----------------------------------------------------------

@dataclass(frozen=True)
class NombreBruto:
    numero: int
    nombre: str
    id: str
    extension: str

    @property
    def archivo(self) -> str:
        return f"bru{_numero4(self.numero)}_{self.nombre}__{self.id}.{self.extension}"

    @classmethod
    def desde_archivo(cls, nombre_archivo: str) -> "NombreBruto":
        coincidencia = PATRON_BRUTO.match(nombre_archivo)
        if coincidencia is None:
            raise NombreInvalido(f"No es un nombre de Bruto: {nombre_archivo!r}")
        return cls(int(coincidencia["numero"]), coincidencia["nombre"], coincidencia["id"], coincidencia["extension"])


@dataclass(frozen=True)
class NombrePieza:
    numero: int
    nombre: str
    id: str

    @property
    def carpeta(self) -> str:
        return f"pie{_numero4(self.numero)}_{self.nombre}__{self.id}"

    def archivo(self, extension: str) -> str:
        """Archivo horneado dentro de la carpeta de la Pieza."""
        return f"{self.carpeta}.{extension}"

    @classmethod
    def desde_texto(cls, texto: str) -> "NombrePieza":
        coincidencia = PATRON_PIEZA.match(texto)
        if coincidencia is None:
            raise NombreInvalido(f"No es un nombre de Pieza: {texto!r}")
        return cls(int(coincidencia["numero"]), coincidencia["nombre"], coincidencia["id"])


# --- Capítulos, minutos y renders ---------------------------------------------

def codigo_capitulo(numero: int) -> str:
    validar_numero_capitulo(numero)
    return f"cap{numero:04d}"


def numero_capitulo(codigo: str) -> int:
    coincidencia = PATRON_CAPITULO.match(codigo)
    if coincidencia is None:
        raise NombreInvalido(f"No es un código de capítulo: {codigo!r}")
    numero = int(coincidencia["numero"])
    validar_numero_capitulo(numero)
    return numero


def validar_numero_capitulo(numero: int) -> None:
    if not CAPITULO_MINIMO <= numero <= CAPITULO_MAXIMO:
        raise NombreInvalido(f"Capítulo fuera de rango: {numero} (válidos {CAPITULO_MINIMO}–{CAPITULO_MAXIMO})")


def codigo_minuto(numero: int) -> str:
    if not 0 <= numero < MINUTOS_POR_CAPITULO:
        raise NombreInvalido(f"Minuto fuera de rango: {numero}")
    return f"min{numero:02d}"


def numero_minuto(codigo: str) -> int:
    coincidencia = PATRON_MINUTO.match(codigo)
    if coincidencia is None:
        raise NombreInvalido(f"No es un código de minuto: {codigo!r}")
    numero = int(coincidencia["numero"])
    if numero >= MINUTOS_POR_CAPITULO:
        raise NombreInvalido(f"Minuto fuera de rango: {codigo!r}")
    return numero


@dataclass(frozen=True)
class NombreRender:
    """Entregable: un minuto, un rango de minutos o el capítulo completo."""

    capitulo: int
    version: int
    desde: int | None = None  # None = capítulo completo
    hasta: int | None = None
    extension: str = "mp4"
    idioma: str | None = None  # None = todas las pistas en un archivo (o proyecto de un solo idioma)

    @property
    def archivo(self) -> str:
        prefijo = codigo_capitulo(self.capitulo)
        if self.desde is None:
            alcance = "completo"
        elif self.hasta is None or self.hasta == self.desde:
            alcance = codigo_minuto(self.desde)
        else:
            alcance = f"{codigo_minuto(self.desde)}-{self.hasta:02d}"
        sufijo = f"_{_idioma(self.idioma)}" if self.idioma else ""
        return f"{prefijo}_{alcance}_v{_version(self.version)}{sufijo}.{self.extension}"

    @property
    def minutos(self) -> range:
        if self.desde is None:
            return range(MINUTOS_POR_CAPITULO)
        return range(self.desde, (self.hasta if self.hasta is not None else self.desde) + 1)

    @classmethod
    def desde_archivo(cls, nombre_archivo: str) -> "NombreRender":
        coincidencia = PATRON_RENDER.match(nombre_archivo)
        if coincidencia is None:
            raise NombreInvalido(f"No es un nombre de Render: {nombre_archivo!r}")
        desde = coincidencia["desde"]
        hasta = coincidencia["hasta"]
        return cls(
            capitulo=int(coincidencia["capitulo"]),
            version=int(coincidencia["version"]),
            desde=int(desde) if desde is not None else None,
            hasta=int(hasta) if hasta is not None else None,
            extension=coincidencia["extension"],
            idioma=coincidencia["idioma"],
        )


# --- IDs -----------------------------------------------------------------------

def es_id_valido(identificador: str) -> bool:
    return PATRON_ID.match(identificador) is not None


class GeneradorIds:
    """IDs de 6 caracteres hexadecimales, únicos en todo el proyecto."""

    CAPACIDAD = 16 ** LONGITUD_ID

    def __init__(self, usados: set[str] | None = None) -> None:
        self._usados: set[str] = set()
        for identificador in usados or ():
            self.registrar(identificador)

    def registrar(self, identificador: str) -> None:
        if not es_id_valido(identificador):
            raise NombreInvalido(f"ID inválido: {identificador!r}")
        self._usados.add(identificador)

    def liberar(self, identificador: str) -> None:
        self._usados.discard(identificador)

    def en_uso(self, identificador: str) -> bool:
        return identificador in self._usados

    def nuevo(self) -> str:
        if len(self._usados) >= self.CAPACIDAD:
            raise RuntimeError("No quedan IDs libres en el proyecto.")
        while True:
            candidato = secrets.token_hex(LONGITUD_ID // 2)
            if candidato not in self._usados:
                self._usados.add(candidato)
                return candidato

    @property
    def usados(self) -> frozenset[str]:
        return frozenset(self._usados)


# --- Rutas ---------------------------------------------------------------------

def carpeta_capitulo(raiz: Path, capitulo: int) -> Path:
    return raiz / codigo_capitulo(capitulo)


def carpeta_minuto(raiz: Path, capitulo: int, minuto: int) -> Path:
    return carpeta_capitulo(raiz, capitulo) / codigo_minuto(minuto)


def carpeta_global(raiz: Path, capitulo: int) -> Path:
    return carpeta_capitulo(raiz, capitulo) / CARPETA_GLOBAL


def carpeta_render(raiz: Path, capitulo: int) -> Path:
    return carpeta_capitulo(raiz, capitulo) / CARPETA_RENDER


def carpeta_shorts(raiz: Path, capitulo: int) -> Path:
    return carpeta_capitulo(raiz, capitulo) / CARPETA_SHORTS


def _numero4(numero: int) -> str:
    if not 1 <= numero <= 9999:
        raise NombreInvalido(f"Número fuera de rango: {numero}")
    return f"{numero:04d}"


def _idioma(idioma: str) -> str:
    if not re.fullmatch(r"[a-z]{2,3}", idioma):
        raise NombreInvalido(f"Código de idioma inválido: {idioma!r} (ISO 639: 'es', 'en'…)")
    return idioma


def _version(version: int) -> str:
    if not 1 <= version <= 999:
        raise NombreInvalido(f"Versión fuera de rango: {version}")
    return f"{version:03d}"
