"""Efectos: una pila ordenada de operaciones sobre la imagen de un Elemento.

El modelo solo describe el efecto (tipo y parámetros). La implementación de
cada tipo vive en `core/motor/efectos/` (épicas E7 y E19).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from editor.core.modelo.keyframe import Animacion

# Tipos previstos (PROJECT.md, E19).
BRILLO = "brillo"
CONTRASTE = "contraste"
SATURACION = "saturacion"
TEMPERATURA = "temperatura"
LUT = "lut"
DESENFOQUE = "desenfoque"
NITIDEZ = "nitidez"
CROMA = "croma"
MASCARA = "mascara"
VINETA = "vineta"
TIPOS_EFECTO = (BRILLO, CONTRASTE, SATURACION, TEMPERATURA, LUT, DESENFOQUE, NITIDEZ, CROMA, MASCARA, VINETA)



@dataclass(frozen=True)
class Parametro:
    """Parámetro numérico de un efecto: la interfaz dibuja su campo y su keyframe con esto."""

    nombre: str
    minimo: float
    maximo: float
    defecto: float
    unidad: str = ""


@dataclass(frozen=True)
class DescriptorEfecto:
    """Qué parámetros y opciones (texto) tiene un tipo de efecto y sus valores iniciales."""

    tipo: str
    etiqueta: str
    parametros: tuple[Parametro, ...] = ()
    opciones: tuple[tuple[str, str], ...] = ()   # (nombre, valor por defecto)


# Registro ampliable: los plugins (E23) agregan sus tipos con `registrar_tipo_efecto`.
_DESCRIPTORES: dict[str, DescriptorEfecto] = {
    d.tipo: d for d in (
        DescriptorEfecto(BRILLO, "Brillo", (Parametro("valor", -1, 1, 0),)),
        DescriptorEfecto(CONTRASTE, "Contraste", (Parametro("valor", -1, 1, 0),)),
        DescriptorEfecto(SATURACION, "Saturación", (Parametro("valor", -1, 1, 0),)),
        DescriptorEfecto(TEMPERATURA, "Temperatura", (Parametro("valor", -1, 1, 0),)),
        DescriptorEfecto(LUT, "LUT (.cube)", (Parametro("intensidad", 0, 1, 1),), (("archivo", ""),)),
        DescriptorEfecto(DESENFOQUE, "Desenfoque", (Parametro("radio", 0, 100, 4, "px"),)),
        DescriptorEfecto(NITIDEZ, "Nitidez", (Parametro("cantidad", 0, 2, 0.5),)),
        DescriptorEfecto(CROMA, "Croma", (Parametro("tolerancia", 0, 1, 0.3), Parametro("suavidad", 0, 1, 0.1)),
                         (("color", "#00ff00"),)),
        # Máscara: rectángulo o elipse en fracciones del Elemento (0–1); animable para seguir algo.
        DescriptorEfecto(MASCARA, "Máscara", (
            Parametro("centro_x", 0, 1, 0.5), Parametro("centro_y", 0, 1, 0.5),
            Parametro("ancho", 0, 1, 0.6), Parametro("alto", 0, 1, 0.6),
            Parametro("suavidad", 0, 0.5, 0.05), Parametro("invertir", 0, 1, 0),
        ), (("forma", "elipse"),)),
        DescriptorEfecto(VINETA, "Viñeta", (Parametro("intensidad", 0, 1, 0.5), Parametro("radio", 0.2, 1.5, 0.8))),
    )
}


def registrar_tipo_efecto(tipo: str, descriptor: DescriptorEfecto | None = None) -> None:
    """Sin descriptor, el tipo queda registrado pero sin parámetros editables en la interfaz."""
    if descriptor is not None:
        _DESCRIPTORES[tipo] = descriptor
    else:
        _DESCRIPTORES.setdefault(tipo, DescriptorEfecto(tipo, tipo))


def es_tipo_efecto(tipo: str) -> bool:
    return tipo in _DESCRIPTORES


def tipos_efecto() -> list[str]:
    return sorted(_DESCRIPTORES)


def descriptor_efecto(tipo: str) -> DescriptorEfecto:
    return _DESCRIPTORES.get(tipo) or DescriptorEfecto(tipo, tipo)


def efecto_nuevo(tipo: str) -> "Efecto":
    """Efecto con los valores iniciales de su descriptor (lo que agrega la interfaz)."""
    descriptor = descriptor_efecto(tipo)
    return Efecto(tipo, {p.nombre: float(p.defecto) for p in descriptor.parametros}, dict(descriptor.opciones))


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
