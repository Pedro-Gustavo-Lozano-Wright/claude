"""Granularidad del tiempo: Capítulo → Minuto → Segundo → Fotograma.

Internamente todo tiempo es un número entero de fotogramas a 24 fps. Minuto,
segundo, fotograma, timecode y los fragmentos de nombre de archivo son vistas
calculadas de ese número (PROJECT.md, sección 6).

Fragmentos de nombre:
    inicio    "min02_seg12f08"
    duración  "dur05s00" o, desde un minuto, "dur01m05s00"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from editor.core.estandar import (
    FOTOGRAMAS_POR_CAPITULO,
    FOTOGRAMAS_POR_MINUTO,
    FOTOGRAMAS_POR_SEGUNDO,
    FPS,
    MINUTOS_POR_CAPITULO,
    SEGUNDOS_POR_MINUTO,
)

_PATRON_INICIO = re.compile(r"^min(\d{2})_seg(\d{2})f(\d{2})$")
_PATRON_DURACION = re.compile(r"^dur(?:(\d{2})m)?(\d{2})s(\d{2})$")

# Duración máxima expresable en un nombre: 99 m 59 s 23 f.
DURACION_MAXIMA = 99 * FOTOGRAMAS_POR_MINUTO + 59 * FOTOGRAMAS_POR_SEGUNDO + FPS - 1


class ErrorTiempo(ValueError):
    pass


def componer(minuto: int, segundo: int, fotograma: int) -> int:
    """(minuto, segundo, fotograma) → fotograma absoluto del capítulo."""
    if not 0 <= segundo < SEGUNDOS_POR_MINUTO:
        raise ErrorTiempo(f"Segundo fuera de rango: {segundo}")
    if not 0 <= fotograma < FPS:
        raise ErrorTiempo(f"Fotograma fuera de rango: {fotograma}")
    if minuto < 0:
        raise ErrorTiempo(f"Minuto negativo: {minuto}")
    return minuto * FOTOGRAMAS_POR_MINUTO + segundo * FOTOGRAMAS_POR_SEGUNDO + fotograma


def descomponer(fotogramas: int) -> tuple[int, int, int]:
    """Fotograma absoluto → (minuto, segundo, fotograma)."""
    if fotogramas < 0:
        raise ErrorTiempo(f"Tiempo negativo: {fotogramas}")
    minuto, resto = divmod(fotogramas, FOTOGRAMAS_POR_MINUTO)
    segundo, fotograma = divmod(resto, FOTOGRAMAS_POR_SEGUNDO)
    return minuto, segundo, fotograma


def minuto_de(fotograma: int) -> int:
    return fotograma // FOTOGRAMAS_POR_MINUTO


def rango_minuto(minuto: int) -> tuple[int, int]:
    """Fotogramas [inicio, fin) de un minuto del capítulo."""
    validar_minuto(minuto)
    inicio = minuto * FOTOGRAMAS_POR_MINUTO
    return inicio, inicio + FOTOGRAMAS_POR_MINUTO


def validar_minuto(minuto: int) -> None:
    if not 0 <= minuto < MINUTOS_POR_CAPITULO:
        raise ErrorTiempo(f"Minuto fuera del capítulo: {minuto} (válidos 0–{MINUTOS_POR_CAPITULO - 1})")


def dentro_del_capitulo(fotograma: int) -> bool:
    return 0 <= fotograma < FOTOGRAMAS_POR_CAPITULO


def recortar_al_capitulo(inicio: int, fin: int) -> tuple[int, int] | None:
    """Intersección de [inicio, fin) con el capítulo; None si queda vacía."""
    a = max(inicio, 0)
    b = min(fin, FOTOGRAMAS_POR_CAPITULO)
    return (a, b) if a < b else None


def minutos_cruzados(inicio: int, fin: int) -> range:
    """Minutos del capítulo que toca el rango [inicio, fin)."""
    rango = recortar_al_capitulo(inicio, fin)
    if rango is None:
        return range(0)
    return range(minuto_de(rango[0]), minuto_de(rango[1] - 1) + 1)


def a_segundos(fotogramas: int) -> Fraction:
    return Fraction(fotogramas, FPS)


def desde_segundos(segundos: Fraction | float) -> int:
    """Segundos → fotogramas, redondeando al fotograma más cercano."""
    return round(Fraction(segundos) * FPS)


@dataclass(frozen=True, order=True)
class Instante:
    """Un punto en el tiempo del capítulo, en fotogramas."""

    fotograma: int

    def __post_init__(self) -> None:
        if self.fotograma < 0:
            raise ErrorTiempo(f"Instante negativo: {self.fotograma}")

    @classmethod
    def desde_partes(cls, minuto: int, segundo: int, fotograma: int) -> "Instante":
        return cls(componer(minuto, segundo, fotograma))

    @classmethod
    def desde_texto(cls, texto: str) -> "Instante":
        """'min02_seg12f08' → Instante."""
        coincidencia = _PATRON_INICIO.match(texto)
        if coincidencia is None:
            raise ErrorTiempo(f"Inicio mal formado: {texto!r}")
        minuto, segundo, fotograma = (int(g) for g in coincidencia.groups())
        return cls.desde_partes(minuto, segundo, fotograma)

    @property
    def partes(self) -> tuple[int, int, int]:
        return descomponer(self.fotograma)

    @property
    def minuto(self) -> int:
        return self.partes[0]

    @property
    def segundo(self) -> int:
        return self.partes[1]

    @property
    def fotograma_del_segundo(self) -> int:
        return self.partes[2]

    @property
    def en_capitulo(self) -> bool:
        return dentro_del_capitulo(self.fotograma)

    def texto(self) -> str:
        """Fragmento de nombre: 'min02_seg12f08'. Exige un minuto de dos cifras."""
        minuto, segundo, fotograma = self.partes
        if minuto > 99:
            raise ErrorTiempo(f"Minuto no expresable en un nombre: {minuto}")
        return f"min{minuto:02d}_seg{segundo:02d}f{fotograma:02d}"

    def timecode(self) -> str:
        """Timecode legible: '02:12.08'."""
        minuto, segundo, fotograma = self.partes
        return f"{minuto:02d}:{segundo:02d}.{fotograma:02d}"

    def segundos(self) -> Fraction:
        return a_segundos(self.fotograma)

    def __add__(self, fotogramas: int) -> "Instante":
        return Instante(self.fotograma + fotogramas)

    def __sub__(self, otro: "Instante | int") -> int:
        valor = otro.fotograma if isinstance(otro, Instante) else otro
        return self.fotograma - valor

    def __str__(self) -> str:
        return self.timecode()


@dataclass(frozen=True, order=True)
class Duracion:
    """Una cantidad de tiempo, en fotogramas (siempre positiva)."""

    fotogramas: int

    def __post_init__(self) -> None:
        if self.fotogramas <= 0:
            raise ErrorTiempo(f"La duración debe ser positiva: {self.fotogramas}")

    @classmethod
    def desde_partes(cls, minutos: int, segundos: int, fotogramas: int) -> "Duracion":
        return cls(componer(minutos, segundos, fotogramas))

    @classmethod
    def desde_texto(cls, texto: str) -> "Duracion":
        """'dur05s00' o 'dur01m05s00' → Duracion."""
        coincidencia = _PATRON_DURACION.match(texto)
        if coincidencia is None:
            raise ErrorTiempo(f"Duración mal formada: {texto!r}")
        minutos = int(coincidencia.group(1) or 0)
        segundos = int(coincidencia.group(2))
        fotogramas = int(coincidencia.group(3))
        if coincidencia.group(1) is not None and minutos == 0:
            raise ErrorTiempo(f"Duración con minutos en cero: {texto!r}; use 'durSSsFF'.")
        return cls.desde_partes(minutos, segundos, fotogramas)

    @property
    def partes(self) -> tuple[int, int, int]:
        return descomponer(self.fotogramas)

    def texto(self) -> str:
        """Fragmento de nombre: 'dur05s00' o 'dur01m05s00'."""
        if self.fotogramas > DURACION_MAXIMA:
            raise ErrorTiempo(f"Duración no expresable en un nombre: {self.fotogramas} fotogramas")
        minutos, segundos, fotogramas = self.partes
        if minutos:
            return f"dur{minutos:02d}m{segundos:02d}s{fotogramas:02d}"
        return f"dur{segundos:02d}s{fotogramas:02d}"

    def legible(self) -> str:
        """'5s00' o '1m05s00', como en el guion."""
        return self.texto()[3:]

    def segundos(self) -> Fraction:
        return a_segundos(self.fotogramas)

    def __str__(self) -> str:
        return self.legible()


# --- fps de las fuentes (Taller) ----------------------------------------------

FPS_COMUNES: dict[str, Fraction] = {
    "23.976": Fraction(24000, 1001),
    "24": Fraction(24, 1),
    "25": Fraction(25, 1),
    "29.97": Fraction(30000, 1001),
    "30": Fraction(30, 1),
    "48": Fraction(48, 1),
    "50": Fraction(50, 1),
    "59.94": Fraction(60000, 1001),
    "60": Fraction(60, 1),
    "120": Fraction(120, 1),
}


def normalizar_fps(valor: float | Fraction | str) -> Fraction:
    """Convierte un fps aproximado (29.97, '23.976', 30000/1001…) en la fracción exacta más probable."""
    if isinstance(valor, str):
        texto = valor.strip()
        if texto in FPS_COMUNES:
            return FPS_COMUNES[texto]
        valor = Fraction(texto)
    fraccion = Fraction(valor)
    if fraccion <= 0:
        raise ErrorTiempo(f"fps inválido: {valor}")
    for exacto in FPS_COMUNES.values():
        if abs(fraccion - exacto) < Fraction(1, 200):
            return exacto
    return fraccion.limit_denominator(1001)


def texto_fps(fps: Fraction) -> str:
    for texto, exacto in FPS_COMUNES.items():
        if exacto == fps:
            return texto
    return f"{float(fps):.3f}".rstrip("0").rstrip(".")


def fotograma_nativo_a_segundos(fotograma: int, fps: Fraction) -> Fraction:
    return Fraction(fotograma) / fps


def segundos_a_fotograma_nativo(segundos: Fraction, fps: Fraction) -> int:
    """Segundos → fotograma de la fuente que se está mostrando en ese instante."""
    return int(segundos * fps)


def fotogramas_24_de_tramo(fotogramas_nativos: int, fps: Fraction, conservar_tiempo: bool) -> int:
    """Cuántos fotogramas a 24 fps ocupa un tramo de una fuente.

    Con `conservar_tiempo` (métodos tiempo, mezcla, interpolación) se respeta
    la duración real; si no (conformar, cámara lenta) cada fotograma nativo
    pasa a ser un fotograma de 24 fps.
    """
    if fotogramas_nativos <= 0:
        return 0
    if not conservar_tiempo:
        return fotogramas_nativos
    return max(1, round(Fraction(fotogramas_nativos) / fps * FPS))
