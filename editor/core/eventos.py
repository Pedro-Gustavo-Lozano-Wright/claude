"""Bus de eventos: el flujo inverso del núcleo hacia las capas superiores.

Los niveles inferiores publican eventos sin conocer a quién le interesan; los
niveles superiores se suscriben. Así el núcleo nunca importa la interfaz
(PROJECT.md, sección 14.3).

Una suscripción a una clase recibe también los eventos de sus subclases.
Los manejadores se ejecutan en el hilo que publica; la capa `app` es la
responsable de pasarlos al hilo de Flet.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, TypeVar

registro = logging.getLogger(__name__)


@dataclass(frozen=True)
class Evento:
    momento: float = field(default_factory=time.time, kw_only=True)


E = TypeVar("E", bound=Evento)
Manejador = Callable[[E], None]


# --- Proyecto -----------------------------------------------------------------

@dataclass(frozen=True)
class ProyectoAbierto(Evento):
    ruta: str


@dataclass(frozen=True)
class ProyectoCerrado(Evento):
    ruta: str


@dataclass(frozen=True)
class ProyectoGuardado(Evento):
    ruta: str


@dataclass(frozen=True)
class ProyectoModificado(Evento):
    """El modelo tiene cambios que todavía no se reconciliaron con el disco."""


# --- Edición ------------------------------------------------------------------

@dataclass(frozen=True)
class ElementoCambiado(Evento):
    id_elemento: str
    capitulo: int
    minuto: int | None  # None si el Elemento está en Global


@dataclass(frozen=True)
class ElementoQuitado(Evento):
    id_elemento: str
    capitulo: int
    minuto: int | None


@dataclass(frozen=True)
class HistorialCambiado(Evento):
    puede_deshacer: bool
    puede_rehacer: bool
    descripcion_deshacer: str = ""
    descripcion_rehacer: str = ""


@dataclass(frozen=True)
class ShortCambiado(Evento):
    id_short: str
    capitulo: int


# --- Medios y Taller ----------------------------------------------------------

@dataclass(frozen=True)
class BrutoImportado(Evento):
    id_bruto: str


@dataclass(frozen=True)
class PiezaHorneada(Evento):
    id_pieza: str
    version: int


@dataclass(frozen=True)
class BancoListo(Evento):
    id_fuente: str


@dataclass(frozen=True)
class MedioFueraDeLinea(Evento):
    id_referencia: str
    ruta: str


# --- Render -------------------------------------------------------------------

@dataclass(frozen=True)
class MinutoInvalidado(Evento):
    capitulo: int
    minuto: int


@dataclass(frozen=True)
class RenderProgreso(Evento):
    id_trabajo: str
    fraccion: float
    descripcion: str = ""


@dataclass(frozen=True)
class RenderTerminado(Evento):
    id_trabajo: str
    ruta: str
    exito: bool
    mensaje: str = ""


class BusEventos:
    """Publicación y suscripción de eventos, segura entre hilos."""

    def __init__(self) -> None:
        self._manejadores: dict[type[Evento], list[Callable[[Evento], None]]] = defaultdict(list)
        self._candado = threading.RLock()

    def suscribir(self, tipo: type[E], manejador: Callable[[E], None]) -> Callable[[], None]:
        """Registra un manejador y devuelve una función para cancelar la suscripción."""
        with self._candado:
            self._manejadores[tipo].append(manejador)  # type: ignore[arg-type]

        def cancelar() -> None:
            with self._candado:
                lista = self._manejadores.get(tipo, [])
                if manejador in lista:
                    lista.remove(manejador)  # type: ignore[arg-type]

        return cancelar

    def publicar(self, evento: Evento) -> None:
        with self._candado:
            destinatarios = [
                manejador
                for clase in type(evento).__mro__
                if isinstance(clase, type) and issubclass(clase, Evento)
                for manejador in self._manejadores.get(clase, ())
            ]
        for manejador in destinatarios:
            try:
                manejador(evento)
            except Exception:
                registro.exception("Error en un manejador de %s", type(evento).__name__)

    def limpiar(self) -> None:
        with self._candado:
            self._manejadores.clear()
