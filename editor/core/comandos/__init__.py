"""Ediciones con deshacer (nivel N3).

La interfaz nunca modifica el modelo: crea un comando y lo pasa al historial.

    historial = Historial(proyecto, bus)
    historial.ejecutar(MoverElemento(1, "a3f90e", nuevo_inicio=3200))
    historial.deshacer()
"""

from editor.core.comandos.actualizar_fuente import ActualizarFuenteEnCapitulo, actualizar_fuente
from editor.core.comandos.agregar_efecto import (
    ActivarEfecto,
    AgregarEfecto,
    CambiarOpcionEfecto,
    CambiarParametroEfecto,
    ReordenarEfecto,
)
from editor.core.comandos.agregar_elemento import AgregarElemento, DuplicarElemento, PegarElementos
from editor.core.comandos.agregar_keyframe import MoverKeyframe, PonerKeyframe
from editor.core.comandos.cambiar_propiedad import CambiarPropiedad, CambiarVelocidad
from editor.core.comandos.cambiar_transicion import CambiarTransicion
from editor.core.comandos.capas import (
    CambiarEstadoCapa,
    CambiarTituloCapitulo,
    MarcarMinuto,
    MoverMarcador,
    PonerMarcador,
    QuitarMarcador,
)
from editor.core.comandos.colocacion import CerrarHuecos, CongelarFotograma, QuitarRango
from editor.core.comandos.comando import Afectados, Comando, EdicionCapitulo, EdicionRechazada
from editor.core.comandos.compuesto import ComandoCompuesto
from editor.core.comandos.dividir_elemento import DividirElementos
from editor.core.comandos.editar_short import (
    CambiarRangoShort,
    CrearShort,
    MoverVentanaShort,
    PonerKeyframeVentana,
    QuitarShort,
)
from editor.core.comandos.historial import Historial
from editor.core.comandos.mover_elemento import CambiarAGlobal, MoverElemento, MoverElementos, mover_entre_capitulos
from editor.core.comandos.proyecto import CambiarIdiomas
from editor.core.comandos.mover_minuto import IntercambiarMinutos
from editor.core.comandos.operaciones import Alcance, ModoColocacion
from editor.core.comandos.quitar_efecto import QuitarEfecto
from editor.core.comandos.quitar_elemento import QuitarElementos
from editor.core.comandos.quitar_keyframe import QuitarKeyframe
from editor.core.comandos.recortar_elemento import FIN, INICIO, RecortarElemento, RecortarElementos
from editor.core.comandos.ripple import RippleRecorte
from editor.core.comandos.roll import Roll
from editor.core.comandos.separar_audio import SepararAudio
from editor.core.comandos.slide import Slide
from editor.core.comandos.slip import Slip
from editor.core.comandos.taller import (
    AgregarBruto,
    AgregarPieza,
    CambiarRecetaPieza,
    InterpretarFps,
    QuitarBruto,
    QuitarPieza,
)
from editor.core.comandos.transformar_elemento import MoverAncla, TransformarElemento
