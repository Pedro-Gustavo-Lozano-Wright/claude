"""Contenido de los Elementos de texto (capas T).

Un Elemento T no tiene archivo de medios: su gemelo .json es el contenido
(PROJECT.md, 8.5). Las fuentes tipográficas viven en `recursos/fuentes/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

IZQUIERDA = "izquierda"
CENTRO = "centro"
DERECHA = "derecha"
ALINEACIONES = (IZQUIERDA, CENTRO, DERECHA)

ANIMACIONES_TEXTO = ("ninguna", "fundido", "deslizar-arriba", "deslizar-abajo", "escribir", "escala")
# Descriptor de las animaciones de texto (como efectos y transiciones): nombre visible.
ETIQUETAS_ANIMACION = {
    "ninguna": "Ninguna", "fundido": "Fundido", "deslizar-arriba": "Deslizar hacia arriba",
    "deslizar-abajo": "Deslizar hacia abajo", "escribir": "Máquina de escribir", "escala": "Escala",
}


@dataclass(frozen=True)
class Sombra:
    color: str = "#000000aa"
    desplazamiento_x: float = 2.0
    desplazamiento_y: float = 2.0
    desenfoque: float = 4.0


@dataclass(frozen=True)
class EstiloTexto:
    fuente: str = ""            # archivo en recursos/fuentes/; vacío = fuente del sistema
    tamano: float = 48.0        # píxeles del lienzo
    color: str = "#ffffffff"    # RGBA hexadecimal
    contorno_color: str = "#000000ff"
    contorno_ancho: float = 0.0
    sombra: Sombra | None = None
    alineacion: str = CENTRO
    interlineado: float = 1.2
    ancho_maximo: float = 0.0   # 0 = sin ajuste de línea

    def __post_init__(self) -> None:
        if self.alineacion not in ALINEACIONES:
            raise ValueError(f"Alineación desconocida: {self.alineacion!r}")
        if self.tamano <= 0:
            raise ValueError("El tamaño de la fuente debe ser positivo.")


@dataclass
class ContenidoTexto:
    texto: str = ""
    estilo: EstiloTexto = field(default_factory=EstiloTexto)
    animacion_entrada: str = "ninguna"
    animacion_salida: str = "ninguna"
    duracion_animacion: int = 12  # fotogramas

    def __post_init__(self) -> None:
        for animacion in (self.animacion_entrada, self.animacion_salida):
            if animacion not in ANIMACIONES_TEXTO:
                raise ValueError(f"Animación de texto desconocida: {animacion!r}")
