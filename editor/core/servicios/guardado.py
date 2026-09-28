"""Guardar y autoguardar (T11.4, PROJECT.md 10.3 y 22.5).

Guardar:
1. Cerrar los archivos abiertos por la vista previa (sin lecturas de rutas viejas).
2. Reconciliador → diario → disco.
3. Marca de guardado en el historial y descarte del autosave.
4. Materializaciones pendientes (extraer audio, convertir formatos) como tarea
   de fondo; al terminar, el estado conocido se refresca en el hilo principal.

Autoguardar: instantánea del modelo cada N segundos si hay cambios.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

import av
from PIL import Image

from editor.core.comandos.historial import Historial
from editor.core.eventos import BusEventos, ProyectoGuardado
from editor.core.motor.codificador import escribir_wav
from editor.core.motor.mezclador_audio import FRECUENCIA, FuenteAudio
from editor.core.proyecto_fs import autosave, reconciliador
from editor.core.proyecto_fs.escaner import Apertura
from editor.core.proyecto_fs.reconciliador import Materializacion, ResultadoGuardado
from editor.core.tareas.cola import BANCO_VISIBLE, ColaTareas, Contexto, Tarea

registro = logging.getLogger(__name__)

EnHiloPrincipal = Callable[[Callable[[], None]], None]


def materializar(raiz: Path, pendientes: list[Materializacion], contexto: Contexto) -> list[str]:
    """Tarea de fondo: crea los archivos que el reconciliador no pudo copiar tal cual."""
    errores = []
    for i, pendiente in enumerate(pendientes):
        contexto.progreso(i / max(1, len(pendientes)), f"Preparando {Path(pendiente.destino).name}")
        if pendiente.origen is None:
            errores.append(f"{pendiente.destino}: {pendiente.motivo}")
            continue
        origen = raiz / pendiente.origen
        destino = raiz / pendiente.destino
        temporal = destino.with_name(f".{destino.name}.parcial{destino.suffix}")
        try:
            if destino.suffix == ".wav":
                fuente = FuenteAudio(origen)
                with av.open(str(origen)) as contenedor:
                    segundos = contenedor.duration / av.time_base if contenedor.duration else 0.0
                escribir_wav(temporal, fuente.leer(0, int(segundos * FRECUENCIA)))
            elif destino.suffix == ".png":
                with Image.open(origen) as imagen:
                    imagen.convert("RGBA").save(temporal, format="PNG")
            else:
                errores.append(f"{pendiente.destino}: conversión no soportada ({pendiente.motivo})")
                continue
            temporal.replace(destino)
        except Exception as error:  # noqa: BLE001
            temporal.unlink(missing_ok=True)
            errores.append(f"{pendiente.destino}: {error}")
    contexto.progreso(1.0, "Archivos preparados")
    return errores


class ServicioGuardado:
    def __init__(
        self,
        apertura: Apertura,
        historial: Historial,
        bus: BusEventos | None = None,
        cola: ColaTareas | None = None,
        en_hilo_principal: EnHiloPrincipal = lambda funcion: funcion(),
        al_cerrar_archivos: Callable[[], None] | None = None,
        autosave_segundos: int = 120,
    ) -> None:
        self.apertura = apertura
        self.historial = historial
        self.bus = bus
        self.cola = cola
        self.en_hilo_principal = en_hilo_principal
        self.al_cerrar_archivos = al_cerrar_archivos
        self.autosave_segundos = autosave_segundos
        self._ultimo_autosave = time.monotonic()

    @property
    def proyecto(self):
        return self.apertura.proyecto

    def guardar(self, forzar: bool = False) -> ResultadoGuardado:
        if self.al_cerrar_archivos is not None:
            self.al_cerrar_archivos()
        resultado = reconciliador.guardar(
            self.proyecto, self.apertura.estado, solo_lectura=self.apertura.solo_lectura, forzar=forzar
        )
        if not resultado.guardado:
            return resultado
        self.historial.marcar_guardado()
        assert self.proyecto.raiz is not None
        autosave.descartar_instantanea(self.proyecto.raiz)
        if self.bus is not None:
            self.bus.publicar(ProyectoGuardado(str(self.proyecto.raiz)))
        materializables = [p for p in resultado.pendientes if p.origen is not None]
        if materializables:
            self._materializar(materializables)
        return resultado

    def _materializar(self, pendientes: list[Materializacion]) -> None:
        raiz = self.proyecto.raiz
        assert raiz is not None

        def refrescar(_resultado, error) -> None:
            if error is not None:
                registro.error("Falló la preparación de archivos: %s", error)
            self.en_hilo_principal(lambda: reconciliador.refrescar_estado(self.proyecto, self.apertura.estado))

        if self.cola is None:
            from editor.core.tareas.cola import ejecutar_ahora

            errores = ejecutar_ahora(lambda contexto: materializar(raiz, pendientes, contexto), "materializar", self.bus)
            for error in errores:
                registro.warning("%s", error)
            reconciliador.refrescar_estado(self.proyecto, self.apertura.estado)
            return
        self.cola.enviar(Tarea(
            "materializar", "Preparar archivos",
            lambda contexto: materializar(raiz, pendientes, contexto),
            prioridad=BANCO_VISIBLE, al_terminar=refrescar,
        ))

    def autoguardar_si_hace_falta(self) -> bool:
        """La app lo llama periódicamente (p. ej. cada 10 s). Devuelve True si guardó una instantánea."""
        if not self.historial.hay_cambios or self.apertura.solo_lectura:
            return False
        if time.monotonic() - self._ultimo_autosave < self.autosave_segundos:
            return False
        autosave.guardar_instantanea(self.proyecto)
        self._ultimo_autosave = time.monotonic()
        return True

