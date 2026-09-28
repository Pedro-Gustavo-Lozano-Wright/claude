"""Funciones numéricas pequeñas usadas por todo el núcleo."""

from __future__ import annotations

import math


def limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def lerp(a: float, b: float, t: float) -> float:
    """Interpolación lineal entre a y b, con t en [0, 1]."""
    return a + (b - a) * t


def fraccion_entre(a: float, b: float, valor: float) -> float:
    """Inversa de lerp: dónde cae valor entre a y b, en [0, 1]."""
    if b == a:
        return 0.0
    return limitar((valor - a) / (b - a), 0.0, 1.0)


def redondear_par(valor: float) -> int:
    """Entero par más cercano; los códecs yuv420p exigen dimensiones pares."""
    entero = int(round(valor))
    return entero if entero % 2 == 0 else entero + 1


def casi_igual(a: float, b: float, tolerancia: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=tolerancia, abs_tol=tolerancia)


def bezier_cubica(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    u = 1.0 - t
    return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3


def derivada_bezier_cubica(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    u = 1.0 - t
    return 3 * u * u * (p1 - p0) + 6 * u * t * (p2 - p1) + 3 * t * t * (p3 - p2)
