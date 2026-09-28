"""Transformación espacial de un Elemento en píxeles del lienzo.

Todas las propiedades se combinan en una sola matriz afín (PROJECT.md, 7.3):

    M = Trasladar(x, y) · Rotar(rotacion) · Escalar(escala_x, escala_y) · Trasladar(-ancla_x, -ancla_y)

La matriz lleva coordenadas del Elemento (píxeles de su archivo, sin recortar)
a coordenadas del lienzo. El recorte solo enmascara una parte del Elemento; no
cambia la matriz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from editor.core.espacio.geometria import Punto, Rect

NORMAL = "normal"
MULTIPLICAR = "multiplicar"
PANTALLA = "pantalla"
SUPERPONER = "superponer"
SUMAR = "sumar"
MODOS_MEZCLA = (NORMAL, MULTIPLICAR, PANTALLA, SUPERPONER, SUMAR)

ORIGINAL = "original"
ENCAJAR = "encajar"
LLENAR = "llenar"
ESTIRAR = "estirar"
AJUSTES_INICIALES = (ORIGINAL, ENCAJAR, LLENAR, ESTIRAR)

# Propiedades numéricas que se pueden animar con keyframes.
PROPIEDADES_ANIMABLES = (
    "x", "y", "ancla_x", "ancla_y", "escala_x", "escala_y", "rotacion", "opacidad",
)

ESCALA_MINIMA = 1e-4


@dataclass(frozen=True)
class Afin:
    """Matriz afín 2×3:  x' = a·x + b·y + c ;  y' = d·x + e·y + f."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0
    e: float = 1.0
    f: float = 0.0

    @classmethod
    def traslacion(cls, dx: float, dy: float) -> "Afin":
        return cls(1.0, 0.0, dx, 0.0, 1.0, dy)

    @classmethod
    def escala(cls, sx: float, sy: float | None = None) -> "Afin":
        return cls(sx, 0.0, 0.0, 0.0, sx if sy is None else sy, 0.0)

    @classmethod
    def rotacion(cls, grados: float) -> "Afin":
        """Rotación en sentido horario (con el eje Y hacia abajo)."""
        radianes = math.radians(grados)
        coseno, seno = math.cos(radianes), math.sin(radianes)
        return cls(coseno, -seno, 0.0, seno, coseno, 0.0)

    def __matmul__(self, otra: "Afin") -> "Afin":
        """Composición: (self @ otra)(p) = self(otra(p))."""
        return Afin(
            self.a * otra.a + self.b * otra.d,
            self.a * otra.b + self.b * otra.e,
            self.a * otra.c + self.b * otra.f + self.c,
            self.d * otra.a + self.e * otra.d,
            self.d * otra.b + self.e * otra.e,
            self.d * otra.c + self.e * otra.f + self.f,
        )

    def aplicar(self, punto: Punto) -> Punto:
        return Punto(self.a * punto.x + self.b * punto.y + self.c, self.d * punto.x + self.e * punto.y + self.f)

    @property
    def determinante(self) -> float:
        return self.a * self.e - self.b * self.d

    def inversa(self) -> "Afin":
        det = self.determinante
        if abs(det) < 1e-12:
            raise ValueError("La matriz no es invertible (escala cero).")
        a, b, c, d, e, f = self.a / det, self.b / det, self.c, self.d / det, self.e / det, self.f
        return Afin(e, -b, b * f - e * c, -d, a, d * c - a * f)

    def como_lista(self) -> list[list[float]]:
        """Formato 2×3 que espera cv2.warpAffine."""
        return [[self.a, self.b, self.c], [self.d, self.e, self.f]]


@dataclass(frozen=True)
class Recorte:
    """Píxeles que se ocultan de cada borde del Elemento."""

    izquierda: float = 0.0
    arriba: float = 0.0
    derecha: float = 0.0
    abajo: float = 0.0

    @classmethod
    def desde_lista(cls, valores: list[float] | tuple[float, ...]) -> "Recorte":
        if len(valores) != 4:
            raise ValueError("El recorte necesita cuatro valores: izq, arr, der, abj.")
        return cls(*(float(v) for v in valores))

    def como_lista(self) -> list[float]:
        return [self.izquierda, self.arriba, self.derecha, self.abajo]

    def region_visible(self, ancho: float, alto: float) -> Rect:
        """Parte del Elemento que queda tras el recorte, en sus propias coordenadas."""
        return Rect.desde_bordes(self.izquierda, self.arriba, ancho - self.derecha, alto - self.abajo)

    @property
    def nulo(self) -> bool:
        return not any((self.izquierda, self.arriba, self.derecha, self.abajo))


@dataclass(frozen=True)
class Transform:
    """Puesta en escena de un Elemento sobre el lienzo (PROJECT.md, 7.2)."""

    x: float = 0.0
    y: float = 0.0
    ancla_x: float = 0.0
    ancla_y: float = 0.0
    escala_x: float = 1.0
    escala_y: float = 1.0
    rotacion: float = 0.0
    recorte: Recorte = Recorte()
    opacidad: float = 1.0
    mezcla: str = NORMAL

    def __post_init__(self) -> None:
        if self.mezcla not in MODOS_MEZCLA:
            raise ValueError(f"Modo de mezcla desconocido: {self.mezcla!r}")
        if abs(self.escala_x) < ESCALA_MINIMA or abs(self.escala_y) < ESCALA_MINIMA:
            raise ValueError("La escala no puede ser cero.")
        if not 0.0 <= self.opacidad <= 1.0:
            object.__setattr__(self, "opacidad", min(1.0, max(0.0, self.opacidad)))

    def matriz(self) -> Afin:
        return (
            Afin.traslacion(self.x, self.y)
            @ Afin.rotacion(self.rotacion)
            @ Afin.escala(self.escala_x, self.escala_y)
            @ Afin.traslacion(-self.ancla_x, -self.ancla_y)
        )

    def matriz_a_resolucion(self, factor: float) -> Afin:
        """Matriz para un destino escalado (vista previa al 20 %, Short, 4K…)."""
        return Afin.escala(factor) @ self.matriz()

    def con(self, **cambios: object) -> "Transform":
        return replace(self, **cambios)

    def con_valores(self, valores: dict[str, float]) -> "Transform":
        """Copia con propiedades animables sustituidas (resultado de evaluar keyframes)."""
        validos = {clave: valor for clave, valor in valores.items() if clave in PROPIEDADES_ANIMABLES}
        return replace(self, **validos) if validos else self

    def mover_ancla(self, ancla_x: float, ancla_y: float) -> "Transform":
        """Cambia el ancla compensando x, y para que el Elemento no se mueva en el lienzo."""
        nueva_posicion = self.matriz().aplicar(Punto(ancla_x, ancla_y))
        return replace(self, ancla_x=ancla_x, ancla_y=ancla_y, x=nueva_posicion.x, y=nueva_posicion.y)

    @property
    def es_identidad(self) -> bool:
        return (
            self.x == 0 and self.y == 0 and self.escala_x == 1 and self.escala_y == 1
            and self.rotacion == 0 and self.recorte.nulo
        )


def transform_inicial(ancho: float, alto: float, lienzo_ancho: float, lienzo_alto: float, ajuste: str) -> Transform:
    """Transform con el que nace un Elemento al colocarlo, según su ajuste inicial.

    El ancla queda en la esquina superior izquierda del Elemento, de modo que
    x, y es su esquina superior izquierda en el lienzo.
    """
    if ajuste not in AJUSTES_INICIALES:
        raise ValueError(f"Ajuste inicial desconocido: {ajuste!r}")
    if ancho <= 0 or alto <= 0 or ajuste == ORIGINAL:
        return Transform()
    if ajuste == ESTIRAR:
        return Transform(escala_x=lienzo_ancho / ancho, escala_y=lienzo_alto / alto)
    factores = (lienzo_ancho / ancho, lienzo_alto / alto)
    escala = min(factores) if ajuste == ENCAJAR else max(factores)
    return Transform(
        x=(lienzo_ancho - ancho * escala) / 2,
        y=(lienzo_alto - alto * escala) / 2,
        escala_x=escala,
        escala_y=escala,
    )
