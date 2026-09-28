"""Curvas de interpolación entre keyframes.

Cada curva transforma el avance lineal t ∈ [0, 1] entre dos keyframes en un
avance suavizado. Las curvas con nombre son equivalentes a las de CSS; la
curva "bezier" recibe dos puntos de control como `cubic-bezier(x1, y1, x2, y2)`.
"""

from __future__ import annotations

from typing import Callable, Sequence

from editor.core.utiles.matematicas import bezier_cubica, derivada_bezier_cubica, limitar

Curva = Callable[[float], float]

CONSTANTE = "constante"
LINEAL = "lineal"
EASE_IN = "ease-in"
EASE_OUT = "ease-out"
EASE_IN_OUT = "ease-in-out"
BEZIER = "bezier"

CONTROLES_PREDEFINIDOS: dict[str, tuple[float, float, float, float]] = {
    EASE_IN: (0.42, 0.0, 1.0, 1.0),
    EASE_OUT: (0.0, 0.0, 0.58, 1.0),
    EASE_IN_OUT: (0.42, 0.0, 0.58, 1.0),
}

NOMBRES_CURVAS = (CONSTANTE, LINEAL, EASE_IN, EASE_OUT, EASE_IN_OUT, BEZIER)


def curva_bezier(x1: float, y1: float, x2: float, y2: float) -> Curva:
    """Curva cúbica con extremos (0, 0) y (1, 1), resuelta en x por Newton y bisección."""
    x1 = limitar(x1, 0.0, 1.0)
    x2 = limitar(x2, 0.0, 1.0)

    def resolver_parametro(x: float) -> float:
        t = x
        for _ in range(8):
            error = bezier_cubica(t, 0.0, x1, x2, 1.0) - x
            if abs(error) < 1e-7:
                return t
            pendiente = derivada_bezier_cubica(t, 0.0, x1, x2, 1.0)
            if abs(pendiente) < 1e-6:
                break
            t -= error / pendiente
        bajo, alto = 0.0, 1.0
        t = x
        for _ in range(40):
            valor = bezier_cubica(t, 0.0, x1, x2, 1.0)
            if abs(valor - x) < 1e-7:
                break
            if valor < x:
                bajo = t
            else:
                alto = t
            t = (bajo + alto) / 2
        return t

    def curva(x: float) -> float:
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        return bezier_cubica(resolver_parametro(x), 0.0, y1, y2, 1.0)

    return curva


_CURVAS: dict[str, Curva] = {
    CONSTANTE: lambda t: 0.0 if t < 1.0 else 1.0,
    LINEAL: lambda t: limitar(t, 0.0, 1.0),
    **{nombre: curva_bezier(*controles) for nombre, controles in CONTROLES_PREDEFINIDOS.items()},
}


def obtener_curva(nombre: str, controles: Sequence[float] | None = None) -> Curva:
    if nombre == BEZIER:
        if controles is None or len(controles) != 4:
            raise ValueError("La curva bezier necesita cuatro valores de control.")
        return curva_bezier(*controles)
    try:
        return _CURVAS[nombre]
    except KeyError:
        raise ValueError(f"Curva desconocida: {nombre!r}") from None


def interpolar(
    valor_a: float,
    valor_b: float,
    t: float,
    curva: str = LINEAL,
    controles: Sequence[float] | None = None,
) -> float:
    avance = obtener_curva(curva, controles)(limitar(t, 0.0, 1.0))
    return valor_a + (valor_b - valor_a) * avance
