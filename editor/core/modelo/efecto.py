"""Efectos: una pila ordenada de operaciones sobre la imagen de un Elemento.

El modelo solo describe el efecto (tipo y parámetros). La implementación de
cada tipo vive en `core/motor/efectos/` (épicas E7 y E17).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from editor.core.modelo.keyframe import Animacion

# Tipos previstos (PROJECT.md, E17).
BRILLO = "brillo"
CONTRASTE = "contraste"
SATURACION = "saturacion"
TEMPERATURA = "temperatura"
LUT = "lut"
DESENFOQUE = "desenfoque"
NITIDEZ = "nitidez"
CROMA = "croma"
TIPOS_EFECTO = (BRILLO, CONTRASTE, SATURACION, TEMPERATURA, LUT, DESENFOQUE, NITIDEZ, CROMA)


@dataclass
class Efecto:
    tipo: str
    parametros: dict[str, float] = field(default_factory=dict)
    # Parámetros de texto (por ejemplo, el archivo .cube de un LUT en recursos/luts/).
    opciones: dict[str, str] = field(default_factory=dict)
    activo: bool = True
    animacion: Animacion = field(default_factory=Animacion)

    def valor(self, parametro: str, f: float) -> float:
        return self.animacion.valor(parametro, f, self.parametros.get(parametro, 0.0))

    def valores_en(self, f: float) -> dict[str, float]:
        resultado = dict(self.parametros)
        resultado.update(self.animacion.valores(f, self.parametros))
        return resultado
