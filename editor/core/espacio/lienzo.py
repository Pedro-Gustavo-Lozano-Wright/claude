"""El lienzo 1280×720 y la regla del marco espacial.

Lo que está dentro del lienzo se ve; lo que está fuera existe pero no se
procesa (PROJECT.md, sección 4.1). Este módulo calcula qué parte de cada
Elemento cae dentro, para descartar lo invisible y transformar solo la región
de interés.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from editor.core.espacio.geometria import Punto, Rect, RectEntero
from editor.core.espacio.transform import Transform
from editor.core.estandar import LIENZO_ALTO, LIENZO_ANCHO, VENTANA_VERTICAL_ANCHO

MARGEN_ACCION = 0.05
MARGEN_TITULOS = 0.10


class Visibilidad(Enum):
    FUERA = "fuera"
    PARCIAL = "parcial"
    DENTRO = "dentro"


@dataclass(frozen=True)
class Lienzo:
    ancho: int = LIENZO_ANCHO
    alto: int = LIENZO_ALTO

    @property
    def rect(self) -> Rect:
        return Rect(0, 0, self.ancho, self.alto)

    @property
    def centro(self) -> Punto:
        return self.rect.centro

    def factor_hacia(self, ancho_destino: int) -> float:
        """Factor de escala para renderizar a otra resolución con la misma relación de aspecto."""
        return ancho_destino / self.ancho

    # --- Elementos sobre el lienzo ---------------------------------------------

    def esquinas(self, transform: Transform, ancho: float, alto: float) -> tuple[Punto, ...]:
        """Esquinas de la parte visible (tras el recorte) del Elemento, en el lienzo."""
        region = transform.recorte.region_visible(ancho, alto)
        matriz = transform.matriz()
        return tuple(matriz.aplicar(esquina) for esquina in region.esquinas())

    def rect_ocupado(self, transform: Transform, ancho: float, alto: float) -> Rect:
        """Rectángulo envolvente del Elemento en el lienzo (puede salirse del lienzo)."""
        if transform.recorte.region_visible(ancho, alto).vacio:
            return Rect(0, 0, 0, 0)
        return Rect.envolvente(self.esquinas(transform, ancho, alto))

    def visibilidad(self, transform: Transform, ancho: float, alto: float) -> Visibilidad:
        ocupado = self.rect_ocupado(transform, ancho, alto)
        if ocupado.vacio or transform.opacidad <= 0.0:
            return Visibilidad.FUERA
        interseccion = ocupado.interseccion(self.rect)
        if interseccion is None:
            return Visibilidad.FUERA
        if interseccion == ocupado:
            return Visibilidad.DENTRO
        return Visibilidad.PARCIAL

    def region_interes(
        self, transform: Transform, ancho: float, alto: float, factor: float = 1.0
    ) -> RectEntero | None:
        """Región de píxeles del destino que hay que calcular; None si no se ve nada.

        `factor` permite obtenerla para un destino escalado (vista previa, Short).
        """
        ocupado = self.rect_ocupado(transform, ancho, alto)
        interseccion = ocupado.interseccion(self.rect) if not ocupado.vacio else None
        if interseccion is None or transform.opacidad <= 0.0:
            return None
        destino = self.rect.escalado(factor)
        region = interseccion.escalado(factor).a_pixeles()
        limite = destino.a_pixeles()
        recorte = region.a_rect().interseccion(limite.a_rect())
        if recorte is None:
            return None
        resultado = RectEntero(int(recorte.x), int(recorte.y), int(recorte.ancho), int(recorte.alto))
        return None if resultado.vacio else resultado

    # --- Guías y márgenes ------------------------------------------------------

    def margen_seguro(self, porcentaje: float) -> Rect:
        return self.rect.reducido(self.ancho * porcentaje, self.alto * porcentaje)

    def guias(self) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """Guías de imán del lienzo: bordes y centro en X y en Y."""
        return (0.0, self.ancho / 2, float(self.ancho)), (0.0, self.alto / 2, float(self.alto))

    # --- Ventana vertical de los Shorts ----------------------------------------

    def ventana_vertical(self, x: float, zoom: float = 1.0) -> Rect:
        """Ventana 9:16 sobre el lienzo (PROJECT.md, 13.5).

        Con zoom 1 ocupa toda la altura (405×720). Con zoom > 1 es más pequeña y
        queda centrada en vertical. `x` es su borde izquierdo y se limita para
        que la ventana nunca salga del lienzo.
        """
        zoom = max(1.0, zoom)
        alto = self.alto / zoom
        ancho = VENTANA_VERTICAL_ANCHO * (self.alto / LIENZO_ALTO) / zoom
        x = min(max(0.0, x), self.ancho - ancho)
        y = (self.alto - alto) / 2
        return Rect(x, y, ancho, alto)

    def x_ventana_centrada(self, zoom: float = 1.0) -> float:
        ventana = self.ventana_vertical(0.0, zoom)
        return (self.ancho - ventana.ancho) / 2


LIENZO = Lienzo()
