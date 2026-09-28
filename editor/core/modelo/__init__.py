"""Modelo del proyecto (nivel N2): Proyecto → Capítulo → Minuto → Elemento.

Solo describe el estado y sus reglas. Lo modifican los comandos (N3), lo
guarda `proyecto_fs` (N3) y lo dibuja el motor (N3).
"""

from editor.core.modelo.bruto import Bruto, TipoMedio
from editor.core.modelo.capa import Capa, TipoCapa
from editor.core.modelo.capitulo import Capitulo, RegistroRender
from editor.core.modelo.composicion import Composicion
from editor.core.modelo.efecto import Efecto
from editor.core.modelo.elemento import (
    AudioElemento,
    Elemento,
    EstadoElemento,
    ReferenciaFuente,
    TiempoElemento,
    TipoFuente,
)
from editor.core.modelo.errores import ErrorModelo, NoEncontrado, Solapamiento
from editor.core.modelo.global_ import Global
from editor.core.modelo.keyframe import Animacion, Keyframe, PistaKeyframes
from editor.core.modelo.minuto import EstadoRender, EstadoTrabajo, Minuto, RegistroRenderMinuto
from editor.core.modelo.pieza import AudioConformado, Horneado, MetodoConversionFps, Pieza, TramoFuente
from editor.core.modelo.proyecto import Proyecto
from editor.core.modelo.referencias import IndiceReferencias, Ubicacion
from editor.core.modelo.short import RegistroRenderShort, Short, VentanaVertical
from editor.core.modelo.taller import Taller
from editor.core.modelo.texto import ContenidoTexto, EstiloTexto, Sombra
from editor.core.modelo.transicion import Transicion

__all__ = [
    "Animacion", "AudioConformado", "AudioElemento", "Bruto", "Capa", "Capitulo", "Composicion",
    "ContenidoTexto", "Efecto", "Elemento", "ErrorModelo", "EstadoElemento", "EstadoRender",
    "EstadoTrabajo", "EstiloTexto", "Global", "Horneado", "IndiceReferencias", "Keyframe",
    "MetodoConversionFps", "Minuto", "NoEncontrado", "Pieza", "PistaKeyframes", "Proyecto",
    "ReferenciaFuente", "RegistroRender", "RegistroRenderMinuto", "RegistroRenderShort", "Short",
    "Solapamiento", "Sombra", "Taller", "TiempoElemento", "TipoCapa", "TipoFuente", "TipoMedio",
    "TramoFuente", "Transicion", "Ubicacion", "VentanaVertical",
]
