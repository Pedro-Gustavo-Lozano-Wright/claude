"""Aplicación Flet: arranque, inicio ↔ proyecto, diálogos y cierre.

`lanzar()` lo llama `main.py`. La función de Flet (`principal`) crea una
`Aplicacion` por ventana; esta muestra la pantalla de inicio o la `Ventana`
del proyecto abierto y se encarga de cerrar sin perder cambios.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import flet as ft

from editor.app.controladores import proyecto as ctl_proyecto
from editor.app.estado import Sesion, hacer_en_principal
from editor.app.ui.tema import TEMA
from editor.core.ajustes import Ajustes
from editor.core.estandar import Estandar
from editor.core.eventos import BusEventos, ProyectoCerrado

registro = logging.getLogger(__name__)

Accion = tuple[str, Callable[[], None] | None]


class Aplicacion:
    def __init__(self, page: ft.Page, ajustes: Ajustes, bus: BusEventos, estandar: Estandar) -> None:
        self.page = page
        self.ajustes = ajustes
        self.bus = bus
        self.estandar = estandar
        self.en_principal = hacer_en_principal(page)
        self.ventana = None
        self._dialogo: ft.AlertDialog | None = None
        # Servicio de Flet: se registra en la página al construirse (necesita zenity en Linux).
        self.selector = ft.FilePicker()

        page.title = "Editor"
        TEMA.aplicar(page)
        page.padding = 0
        page.spacing = 0
        page.window.min_width = 1100
        page.window.min_height = 700
        page.window.prevent_close = True
        page.window.on_event = self._evento_ventana
        page.on_close = self._sesion_terminada

    # --- Pantallas ---------------------------------------------------------------------

    def mostrar_inicio(self) -> None:
        from editor.app.ui.inicio import Inicio

        self.page.title = "Editor"
        self.page.on_keyboard_event = None
        self.page.controls.clear()
        self.page.add(Inicio(self).control)
        self.page.update()

    def abrir(self, ruta: Path, solo_lectura: bool = False) -> None:
        if self.ventana is not None:
            self.ventana.pedir_cierre(lambda: self.abrir(ruta, solo_lectura))
            return
        resultado = ctl_proyecto.abrir(ruta, self.ajustes, self.bus, self.en_principal, solo_lectura=solo_lectura)
        if resultado.bloqueado_por is not None:
            info = resultado.bloqueado_por
            self.dialogo(
                "Proyecto en uso",
                f"Otra instancia tiene abierto el proyecto (equipo {info.equipo}, proceso {info.pid}, desde {info.fecha}).",
                [("Abrir en solo lectura", lambda: self.abrir(ruta, solo_lectura=True)), ("Cancelar", None)],
            )
            return
        if resultado.sesion is None:
            self.avisar(resultado.error or "No se pudo abrir el proyecto.")
            return
        self._montar(resultado.sesion)
        if resultado.autosave_pendiente:
            self.dialogo(
                "Recuperar trabajo",
                "Hay una instantánea de autosave más reciente que lo guardado. ¿Restaurarla?",
                [("Restaurar", self._restaurar_autosave), ("Descartar", self._descartar_autosave)],
            )
        resumen = ctl_proyecto.resumen_informe(resultado.informe)
        if resumen:
            self.avisar(resumen)

    def crear(self, ruta: Path) -> None:
        if self.ventana is not None:
            self.ventana.pedir_cierre(lambda: self.crear(ruta))
            return
        resultado = ctl_proyecto.crear(ruta, self.ajustes, self.bus, self.en_principal, estandar=self.estandar)
        if resultado.sesion is None:
            self.avisar(resultado.error or "No se pudo crear el proyecto.")
            return
        self._montar(resultado.sesion)

    def _montar(self, sesion: Sesion) -> None:
        from editor.app.ui.ventana import Ventana

        self.ventana = Ventana(self, sesion)
        self.ventana.montar()

    def cerrar_proyecto(self) -> None:
        if self.ventana is None:
            return
        ventana, self.ventana = self.ventana, None
        raiz = ventana.sesion.proyecto.raiz
        ventana.desmontar()
        self.bus.publicar(ProyectoCerrado(str(raiz)))
        self.mostrar_inicio()

    def _restaurar_autosave(self) -> None:
        if self.ventana is None:
            return
        try:
            ctl_proyecto.restaurar_autosave(self.ventana.sesion)
        except Exception as error:  # noqa: BLE001
            self.avisar(f"No se pudo restaurar la instantánea: {error}")
            return
        self.ventana.refrescar()
        self.avisar("Instantánea restaurada: revise y guarde para conservarla.")

    def _descartar_autosave(self) -> None:
        if self.ventana is not None:
            ctl_proyecto.descartar_autosave(self.ventana.sesion)

    # --- Avisos y diálogos -------------------------------------------------------------

    @property
    def hay_dialogo(self) -> bool:
        return self._dialogo is not None

    def avisar(self, texto: str) -> None:
        registro.info("%s", texto)
        self.page.show_dialog(ft.SnackBar(ft.Text(texto), duration=ft.Duration(seconds=5), show_close_icon=True))

    def dialogo(self, titulo: str, contenido: str | ft.Control, acciones: list[Accion]) -> None:
        """Diálogo modal; cada botón lo cierra y ejecuta su acción (None = solo cerrar)."""

        def pulsar(accion: Callable[[], None] | None) -> Callable:
            def manejador(_evento) -> None:
                self.page.pop_dialog()
                self._dialogo = None
                if accion is not None:
                    accion()
            return manejador

        cuerpo = ft.Text(contenido, selectable=True) if isinstance(contenido, str) else contenido
        botones = [
            (ft.FilledButton if i == 0 else ft.TextButton)(texto, on_click=pulsar(accion))
            for i, (texto, accion) in enumerate(acciones)
        ]
        self._dialogo = ft.AlertDialog(modal=True, title=ft.Text(titulo), content=cuerpo, actions=botones,
                                       bgcolor=TEMA.panel_alto)
        self.page.show_dialog(self._dialogo)

    # --- Cierre de la ventana ----------------------------------------------------------

    async def _evento_ventana(self, evento: ft.WindowEvent) -> None:
        if evento.type != ft.WindowEventType.CLOSE:
            return
        if self.ventana is None:
            await self._salir()
            return
        self.ventana.pedir_cierre(lambda: self.page.run_task(self._salir))

    def _sesion_terminada(self, _evento=None) -> None:
        """La conexión con la interfaz terminó sin pasar por el cierre normal: no se pierde nada."""
        if self.ventana is None:
            return
        ventana, self.ventana = self.ventana, None
        sesion = ventana.sesion
        if sesion.historial.hay_cambios and not sesion.solo_lectura:
            try:
                from editor.core.proyecto_fs import autosave

                autosave.guardar_instantanea(sesion.proyecto)
            except Exception:  # noqa: BLE001
                registro.exception("No se pudo guardar la instantánea al cerrar")
        ventana.abandonar()

    async def _salir(self) -> None:
        self.ajustes.guardar_usuario()
        await self.page.window.destroy()


def lanzar(ajustes: Ajustes, bus: BusEventos, estandar: Estandar, ruta: Path | None) -> None:
    """Abre la ventana de escritorio (bloquea hasta cerrarla)."""

    def principal(page: ft.Page) -> None:
        aplicacion = Aplicacion(page, ajustes, bus, estandar)
        destino = ruta
        if destino is None:
            recientes = ctl_proyecto.recientes(ajustes)
            destino = recientes[0] if recientes else None
        if destino is None:
            aplicacion.mostrar_inicio()
            return
        aplicacion.mostrar_inicio()   # queda debajo si la apertura falla o pide un diálogo
        aplicacion.abrir(destino)

    ft.run(principal, assets_dir=str(Path(__file__).parent / "ui" / "recursos"))
