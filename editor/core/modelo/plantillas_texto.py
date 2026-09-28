"""Plantillas de títulos y rótulos (E19).

Una plantilla fija estilo, posición y animaciones de un texto nuevo; después el
texto es un Elemento T como cualquier otro. Los que se centran usan una caja de
ancho fijo (`ancho_maximo`) para que editar el texto no los corra.
"""

from __future__ import annotations

from dataclasses import dataclass

from editor.core.estandar import LIENZO_ALTO, LIENZO_ANCHO
from editor.core.modelo.texto import CENTRO, IZQUIERDA, EstiloTexto, Sombra

SOMBRA_SUAVE = Sombra("#000000aa", 2.0, 2.0, 4.0)


@dataclass(frozen=True)
class PlantillaTexto:
    nombre: str
    etiqueta: str
    estilo: EstiloTexto
    x: float
    y: float
    entrada: str = "fundido"
    salida: str = "fundido"
    duracion_segundos: int = 4


def _centrada(margen: float) -> tuple[float, float]:
    """(x, ancho_maximo) de una caja centrada con `margen` a cada lado."""
    return margen, LIENZO_ANCHO - 2 * margen


_X_TITULO, _ANCHO_TITULO = _centrada(LIENZO_ANCHO * 0.1)
_X_SUB, _ANCHO_SUB = _centrada(LIENZO_ANCHO * 0.1)

PLANTILLAS: dict[str, PlantillaTexto] = {p.nombre: p for p in (
    PlantillaTexto("titulo", "Título centrado",
                   EstiloTexto(tamano=80, alineacion=CENTRO, ancho_maximo=_ANCHO_TITULO, sombra=SOMBRA_SUAVE),
                   _X_TITULO, LIENZO_ALTO * 0.38, "escala", "fundido"),
    PlantillaTexto("rotulo", "Rótulo inferior",
                   EstiloTexto(tamano=40, alineacion=IZQUIERDA, sombra=SOMBRA_SUAVE),
                   LIENZO_ANCHO * 0.1, LIENZO_ALTO * 0.74, "deslizar-arriba", "fundido"),
    PlantillaTexto("subtitulo", "Subtítulo",
                   EstiloTexto(tamano=40, alineacion=CENTRO, ancho_maximo=_ANCHO_SUB,
                               contorno_ancho=3.0, contorno_color="#000000ff"),
                   _X_SUB, LIENZO_ALTO * 0.82, "ninguna", "ninguna", 3),
    PlantillaTexto("creditos", "Créditos",
                   EstiloTexto(tamano=36, alineacion=CENTRO, ancho_maximo=_ANCHO_TITULO, interlineado=1.5),
                   _X_TITULO, LIENZO_ALTO * 0.2, "fundido", "fundido", 6),
)}
