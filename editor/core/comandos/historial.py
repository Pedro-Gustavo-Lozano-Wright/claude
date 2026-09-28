"""Historial de deshacer y rehacer (T6.2).

Uno solo por proyecto. Publica en el bus los eventos que las pantallas y las
huellas necesitan después de cada ejecución, deshacer o rehacer.
"""

from __future__ import annotations

import time

from editor.core.comandos.comando import Afectados, Comando
from editor.core.eventos import (
    BusEventos,
    ElementoAgregado,
    ElementoCambiado,
    ElementoQuitado,
    HistorialCambiado,
    PiezaModificada,
    ProyectoModificado,
    ShortCambiado,
)
from editor.core.modelo.proyecto import Proyecto

VENTANA_FUSION_SEGUNDOS = 1.0


class Historial:
    def __init__(self, proyecto: Proyecto, bus: BusEventos | None = None, limite: int = 100) -> None:
        self.proyecto = proyecto
        self.bus = bus
        self.limite = limite
        self._deshacer: list[Comando] = []
        self._rehacer: list[Comando] = []
        self._ultimo_momento = 0.0
        # Posición de la pila en el último guardado; None si ese estado ya no es alcanzable.
        self._marca_guardado: int | None = 0

    # --- Estado ----------------------------------------------------------------------

    @property
    def puede_deshacer(self) -> bool:
        return bool(self._deshacer)

    @property
    def puede_rehacer(self) -> bool:
        return bool(self._rehacer)

    @property
    def hay_cambios(self) -> bool:
        return self._marca_guardado != len(self._deshacer)

    def marcar_guardado(self) -> None:
        self._marca_guardado = len(self._deshacer)
        self._publicar_estado()

    def vaciar(self) -> None:
        """Olvida los pasos: al cambiar de capítulo (eran del anterior) o tras vaciar la papelera."""
        hay_cambios = self.hay_cambios
        self._deshacer.clear()
        self._rehacer.clear()
        self._marca_guardado = None if hay_cambios else 0
        self._publicar_estado()

    def marcar_sin_guardar(self) -> None:
        """El modelo cambió fuera del historial (p. ej. al restaurar un autosave): hay que guardar."""
        self._marca_guardado = None
        self._publicar_estado()

    def descripciones(self) -> tuple[list[str], list[str]]:
        """Para el panel de historial: (pasos hechos, pasos por rehacer)."""
        return [c.descripcion for c in self._deshacer], [c.descripcion for c in reversed(self._rehacer)]

    # --- Operaciones -------------------------------------------------------------------

    def ejecutar(self, comando: Comando) -> None:
        comando.ejecutar(self.proyecto)
        if self._marca_guardado is not None and self._marca_guardado > len(self._deshacer):
            # El estado guardado estaba en la pila de rehacer, que se descarta.
            self._marca_guardado = None
        ahora = time.monotonic()
        fusionado = (
            bool(self._deshacer)
            and ahora - self._ultimo_momento <= VENTANA_FUSION_SEGUNDOS
            and self._marca_guardado != len(self._deshacer)
            and self._deshacer[-1].fusionar(comando)
        )
        if not fusionado:
            self._deshacer.append(comando)
            if len(self._deshacer) > self.limite:
                del self._deshacer[0]
                if self._marca_guardado is not None:
                    self._marca_guardado -= 1
                    if self._marca_guardado < 0:
                        self._marca_guardado = None
        self._rehacer.clear()
        self._ultimo_momento = ahora
        self._publicar(comando.afectados())

    def deshacer(self) -> Comando | None:
        if not self._deshacer:
            return None
        comando = self._deshacer.pop()
        comando.deshacer(self.proyecto)
        self._rehacer.append(comando)
        self._ultimo_momento = 0.0
        self._publicar([a.invertido() for a in comando.afectados()])
        return comando

    def rehacer(self) -> Comando | None:
        if not self._rehacer:
            return None
        comando = self._rehacer.pop()
        comando.ejecutar(self.proyecto)
        self._deshacer.append(comando)
        self._ultimo_momento = 0.0
        self._publicar(comando.afectados())
        return comando

    def limpiar(self) -> None:
        self._deshacer.clear()
        self._rehacer.clear()
        self._marca_guardado = 0
        self._publicar_estado()

    # --- Eventos -------------------------------------------------------------------------

    def _publicar(self, afectados: list[Afectados]) -> None:
        if self.bus is None:
            return
        for afectado in afectados:
            capitulo = afectado.capitulo
            minutos = tuple(sorted(afectado.minutos))
            if capitulo is not None:
                for identificador in sorted(afectado.agregados):
                    self.bus.publicar(ElementoAgregado(identificador, capitulo, self._minuto(identificador), minutos))
                for identificador in sorted(afectado.cambiados):
                    self.bus.publicar(ElementoCambiado(identificador, capitulo, self._minuto(identificador), minutos))
                for identificador in sorted(afectado.quitados):
                    self.bus.publicar(ElementoQuitado(identificador, capitulo, None, minutos))
                for identificador in sorted(afectado.shorts):
                    self.bus.publicar(ShortCambiado(identificador, capitulo))
            for identificador in sorted(afectado.piezas):
                self.bus.publicar(PiezaModificada(identificador))
        self.bus.publicar(ProyectoModificado())
        self._publicar_estado()

    def _minuto(self, id_elemento: str) -> int | None:
        ubicacion = self.proyecto.referencias.ubicacion(id_elemento)
        return None if ubicacion is None else ubicacion.minuto

    def _publicar_estado(self) -> None:
        if self.bus is None:
            return
        hechos, pendientes = self.descripciones()
        self.bus.publicar(HistorialCambiado(
            puede_deshacer=self.puede_deshacer,
            puede_rehacer=self.puede_rehacer,
            descripcion_deshacer=hechos[-1] if hechos else "",
            descripcion_rehacer=pendientes[0] if pendientes else "",
        ))
