"""Cola de tareas de fondo con prioridades y cancelación (T9.1).

Reglas (PROJECT.md, 22.8):
- Una tarea **nunca** toca el modelo vivo ni llama a `proyecto.capitulo()`:
  recibe una instantánea (copia) de lo que necesita al crearse.
- Informa progreso por el bus (`TareaProgreso`, `TareaTerminada`).
- Su resultado vuelve por `al_terminar`, que se ejecuta en el hilo de trabajo;
  la capa `app` lo pasa al hilo de la interfaz.

Prioridades: 1 = lo que el usuario está mirando … 6 = render final en segundo plano.
"""

from __future__ import annotations

import itertools
import logging
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from editor.core.eventos import BusEventos, TareaProgreso, TareaTerminada

registro = logging.getLogger(__name__)

MONITOR = 1
BANCO_VISIBLE = 2
PRERENDER_ACTUAL = 3
BANCO_RESTO = 4
PRERENDER_RESTO = 5
RENDER_FINAL = 6


class Cancelada(Exception):
    """La tarea se canceló; se lanza desde `Contexto.comprobar()`."""


@dataclass
class Contexto:
    id_tarea: str
    tipo: str
    bus: BusEventos | None
    _evento_cancelar: threading.Event = field(default_factory=threading.Event)

    @property
    def cancelada(self) -> bool:
        return self._evento_cancelar.is_set()

    def comprobar(self) -> None:
        if self.cancelada:
            raise Cancelada(self.id_tarea)

    def progreso(self, fraccion: float, descripcion: str = "") -> None:
        self.comprobar()
        if self.bus is not None:
            self.bus.publicar(TareaProgreso(self.id_tarea, self.tipo, max(0.0, min(1.0, fraccion)), descripcion))


@dataclass
class Tarea:
    tipo: str
    descripcion: str
    funcion: Callable[[Contexto], Any]
    prioridad: int = PRERENDER_RESTO
    al_terminar: Callable[[Any, BaseException | None], None] | None = None
    # Tareas con la misma clave se reemplazan: la nueva cancela a la anterior (p. ej. el pre-render de un minuto).
    clave: str | None = None
    id: str = ""


class ColaTareas:
    def __init__(self, bus: BusEventos | None = None, trabajadores: int = 2) -> None:
        self.bus = bus
        self._cola: queue.PriorityQueue = queue.PriorityQueue()
        self._contador = itertools.count()
        self._contextos: dict[str, Contexto] = {}
        self._por_clave: dict[str, str] = {}
        self._candado = threading.Lock()
        self._activa = True
        self._hilos = [
            threading.Thread(target=self._trabajar, name=f"tarea-{i}", daemon=True) for i in range(max(1, trabajadores))
        ]
        for hilo in self._hilos:
            hilo.start()

    def enviar(self, tarea: Tarea) -> str:
        numero = next(self._contador)
        tarea.id = tarea.id or f"{tarea.tipo}-{numero}"
        contexto = Contexto(tarea.id, tarea.tipo, self.bus)
        with self._candado:
            if tarea.clave is not None:
                anterior = self._por_clave.get(tarea.clave)
                if anterior is not None and anterior in self._contextos:
                    self._contextos[anterior]._evento_cancelar.set()
                self._por_clave[tarea.clave] = tarea.id
            self._contextos[tarea.id] = contexto
        self._cola.put((tarea.prioridad, numero, tarea))
        return tarea.id

    def cancelar(self, id_tarea: str) -> None:
        with self._candado:
            contexto = self._contextos.get(id_tarea)
        if contexto is not None:
            contexto._evento_cancelar.set()

    def pendientes(self) -> int:
        return self._cola.qsize()

    def detener(self, esperar: bool = True) -> None:
        self._activa = False
        with self._candado:
            for contexto in self._contextos.values():
                contexto._evento_cancelar.set()
        for _ in self._hilos:
            self._cola.put((0, -1, None))
        if esperar:
            for hilo in self._hilos:
                hilo.join(timeout=10)

    def _trabajar(self) -> None:
        while True:
            _, _, tarea = self._cola.get()
            if tarea is None or not self._activa:
                return
            with self._candado:
                contexto = self._contextos.get(tarea.id)
            if contexto is None:
                continue
            resultado: Any = None
            error: BaseException | None = None
            try:
                contexto.comprobar()
                resultado = tarea.funcion(contexto)
            except Cancelada as cancelada:
                error = cancelada
            except Exception as fallo:  # noqa: BLE001 — la tarea informa y la cola sigue viva
                registro.exception("Falló la tarea %s", tarea.id)
                error = fallo
            finally:
                with self._candado:
                    self._contextos.pop(tarea.id, None)
                    if tarea.clave is not None and self._por_clave.get(tarea.clave) == tarea.id:
                        del self._por_clave[tarea.clave]
            if self.bus is not None and not isinstance(error, Cancelada):
                self.bus.publicar(TareaTerminada(tarea.id, tarea.tipo, error is None, "" if error is None else str(error)))
            if tarea.al_terminar is not None and not isinstance(error, Cancelada):
                try:
                    tarea.al_terminar(resultado, error)
                except Exception:  # noqa: BLE001
                    registro.exception("Falló al_terminar de %s", tarea.id)


def ejecutar_ahora(funcion: Callable[[Contexto], Any], tipo: str = "directa", bus: BusEventos | None = None) -> Any:
    """Ejecuta una función de tarea en el hilo actual (modo sin interfaz de `main.py`)."""
    return funcion(Contexto(f"{tipo}-directa", tipo, bus))
