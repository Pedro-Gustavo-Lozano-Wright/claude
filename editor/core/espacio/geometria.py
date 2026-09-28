"""Geometría 2D en píxeles del lienzo: puntos, rectángulos e imán.

Convención de todo el editor: origen (0, 0) en la esquina superior izquierda,
X hacia la derecha, Y hacia abajo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Punto:
    x: float
    y: float

    def __add__(self, otro: "Punto") -> "Punto":
        return Punto(self.x + otro.x, self.y + otro.y)

    def __sub__(self, otro: "Punto") -> "Punto":
        return Punto(self.x - otro.x, self.y - otro.y)

    def distancia(self, otro: "Punto") -> float:
        return math.hypot(self.x - otro.x, self.y - otro.y)


@dataclass(frozen=True)
class Rect:
    """Rectángulo alineado a los ejes: esquina superior izquierda + tamaño."""

    x: float
    y: float
    ancho: float
    alto: float

    @classmethod
    def desde_bordes(cls, izquierda: float, arriba: float, derecha: float, abajo: float) -> "Rect":
        return cls(izquierda, arriba, max(0.0, derecha - izquierda), max(0.0, abajo - arriba))

    @classmethod
    def envolvente(cls, puntos: Iterable[Punto]) -> "Rect":
        lista = list(puntos)
        if not lista:
            return cls(0, 0, 0, 0)
        xs = [p.x for p in lista]
        ys = [p.y for p in lista]
        return cls.desde_bordes(min(xs), min(ys), max(xs), max(ys))

    @property
    def izquierda(self) -> float:
        return self.x

    @property
    def arriba(self) -> float:
        return self.y

    @property
    def derecha(self) -> float:
        return self.x + self.ancho

    @property
    def abajo(self) -> float:
        return self.y + self.alto

    @property
    def centro(self) -> Punto:
        return Punto(self.x + self.ancho / 2, self.y + self.alto / 2)

    @property
    def vacio(self) -> bool:
        return self.ancho <= 0 or self.alto <= 0

    @property
    def area(self) -> float:
        return 0.0 if self.vacio else self.ancho * self.alto

    def esquinas(self) -> tuple[Punto, Punto, Punto, Punto]:
        """Superior izquierda, superior derecha, inferior derecha, inferior izquierda."""
        return (
            Punto(self.izquierda, self.arriba),
            Punto(self.derecha, self.arriba),
            Punto(self.derecha, self.abajo),
            Punto(self.izquierda, self.abajo),
        )

    def contiene(self, punto: Punto) -> bool:
        return self.izquierda <= punto.x < self.derecha and self.arriba <= punto.y < self.abajo

    def interseccion(self, otro: "Rect") -> "Rect | None":
        izquierda = max(self.izquierda, otro.izquierda)
        arriba = max(self.arriba, otro.arriba)
        derecha = min(self.derecha, otro.derecha)
        abajo = min(self.abajo, otro.abajo)
        if derecha <= izquierda or abajo <= arriba:
            return None
        return Rect.desde_bordes(izquierda, arriba, derecha, abajo)

    def se_toca_con(self, otro: "Rect") -> bool:
        return self.interseccion(otro) is not None

    def union(self, otro: "Rect") -> "Rect":
        return Rect.desde_bordes(
            min(self.izquierda, otro.izquierda),
            min(self.arriba, otro.arriba),
            max(self.derecha, otro.derecha),
            max(self.abajo, otro.abajo),
        )

    def escalado(self, factor: float) -> "Rect":
        return Rect(self.x * factor, self.y * factor, self.ancho * factor, self.alto * factor)

    def desplazado(self, dx: float, dy: float) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.ancho, self.alto)

    def reducido(self, margen_x: float, margen_y: float) -> "Rect":
        return Rect.desde_bordes(
            self.izquierda + margen_x, self.arriba + margen_y, self.derecha - margen_x, self.abajo - margen_y
        )

    def a_pixeles(self) -> "RectEntero":
        """Rectángulo entero que cubre por completo a este (piso y techo)."""
        izquierda = math.floor(self.izquierda)
        arriba = math.floor(self.arriba)
        derecha = math.ceil(self.derecha)
        abajo = math.ceil(self.abajo)
        return RectEntero(izquierda, arriba, derecha - izquierda, abajo - arriba)


@dataclass(frozen=True)
class RectEntero:
    """Región de píxeles: se usa para recortar arreglos de imagen."""

    x: int
    y: int
    ancho: int
    alto: int

    @property
    def vacio(self) -> bool:
        return self.ancho <= 0 or self.alto <= 0

    @property
    def rebanadas(self) -> tuple[slice, slice]:
        """(filas, columnas) para indexar un arreglo imagen[filas, columnas]."""
        return slice(self.y, self.y + self.alto), slice(self.x, self.x + self.ancho)

    def a_rect(self) -> Rect:
        return Rect(self.x, self.y, self.ancho, self.alto)


# --- Imán ----------------------------------------------------------------------

@dataclass(frozen=True)
class ResultadoIman:
    valor: float
    objetivo: float | None  # None si no hubo imán

    @property
    def ajustado(self) -> bool:
        return self.objetivo is not None


def iman(valor: float, objetivos: Sequence[float], tolerancia: float) -> ResultadoIman:
    """Atrae `valor` al objetivo más cercano si está a menos de `tolerancia`."""
    mejor: float | None = None
    distancia_mejor = tolerancia
    for objetivo in objetivos:
        distancia = abs(valor - objetivo)
        if distancia <= distancia_mejor:
            mejor = objetivo
            distancia_mejor = distancia
    return ResultadoIman(mejor if mejor is not None else valor, mejor)


def iman_rect(
    rect: Rect,
    guias_x: Sequence[float],
    guias_y: Sequence[float],
    tolerancia: float,
) -> tuple[float, float]:
    """Desplazamiento (dx, dy) que pega los bordes o el centro de `rect` a las guías."""

    def mejor_desplazamiento(bordes: Sequence[float], guias: Sequence[float]) -> float:
        elegido = 0.0
        distancia_mejor = tolerancia
        encontrado = False
        for borde in bordes:
            for guia in guias:
                distancia = abs(guia - borde)
                if distancia <= distancia_mejor:
                    elegido = guia - borde
                    distancia_mejor = distancia
                    encontrado = True
        return elegido if encontrado else 0.0

    dx = mejor_desplazamiento((rect.izquierda, rect.centro.x, rect.derecha), guias_x)
    dy = mejor_desplazamiento((rect.arriba, rect.centro.y, rect.abajo), guias_y)
    return dx, dy
