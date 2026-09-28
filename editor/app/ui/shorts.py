"""Espacio de trabajo Shorts (E22).

A la izquierda la lista de Shorts del capítulo con su estado de render; en el
centro la vista vertical (lo que se verá en el Short en el cabezal); a la
derecha el encuadre: posición horizontal y zoom de la ventana 9:16, keyframes
para seguir la acción y el render. El monitor de al lado sigue mostrando el
lienzo 16:9 con la guía 9:16.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import flet as ft

from editor.app.controladores import shorts as ctl
from editor.app.ui.tema import TEMA, texto, texto_suave, titulo_panel
from editor.app.ui.widgets import actualizar, timecode
from editor.app.ui.widgets.imagen import imagen_vacia
from editor.core.espacio.lienzo import LIENZO
from editor.core.servicios import shorts as servicio
from editor.core.tiempo.nomenclatura import carpeta_shorts

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana

ICONOS_ESTADO = {
    servicio.SIN_RENDER: (ft.Icons.RADIO_BUTTON_UNCHECKED, "texto_suave"),
    servicio.AL_DIA: (ft.Icons.CHECK_CIRCLE, "render_al_dia"),
    servicio.DESACTUALIZADO: (ft.Icons.UPDATE, "error"),
}


class PanelShorts:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self.id_short: str | None = None
        self._arrastrando = False
        self._editando = False
        self.lista = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        self.vista = ft.Image(src=imagen_vacia(), gapless_playback=True, fit=ft.BoxFit.CONTAIN,
                              width=ctl.TAMANO_VISTA[0], height=ctl.TAMANO_VISTA[1])
        self.tiempo = ft.Slider(min=0, max=1, value=0, expand=True, on_change=self._mover_tiempo)
        self.tiempo_texto = texto_suave("")
        self.nombre = ft.TextField(label="Nombre", dense=True, text_size=12, on_submit=self._renombrar,
                                   on_blur=self._renombrar, on_focus=self._editar)
        self.x = ft.Slider(min=0, max=LIENZO.ancho, value=0, label="{value}", on_change=self._previsualizar,
                           on_change_end=self._soltar_encuadre)
        self.zoom = ft.Slider(min=1.0, max=3.0, value=1.0, divisions=40, label="{value}×",
                              on_change=self._previsualizar, on_change_end=self._soltar_encuadre)
        self.estado = texto_suave("")
        self.info = texto_suave("")
        self.detalle = ft.Column(
            [
                self.nombre,
                self.info,
                texto("Posición horizontal", 12), self.x,
                texto("Zoom", 12), self.zoom,
                ft.Row([
                    ft.OutlinedButton("Keyframe aquí", icon=ft.Icons.DIAMOND_OUTLINED, on_click=self._keyframe,
                                      tooltip="La ventana pasa por este encuadre en el cabezal (sigue la acción)"),
                    ft.TextButton("Ventana fija", on_click=self._fija, tooltip="Quita los keyframes"),
                ], wrap=True),
                ft.Row([
                    ft.TextButton("Usar rango I–O", on_click=self._rango),
                    ft.TextButton("Ir al inicio", on_click=self._ir_inicio),
                ], wrap=True),
                ft.Divider(),
                ft.Row([
                    ft.FilledButton("Renderizar", icon=ft.Icons.MOVIE, on_click=self._renderizar_este),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Quitar el Short", on_click=self._quitar),
                ]),
                self.estado,
            ],
            spacing=4, scroll=ft.ScrollMode.AUTO, expand=True,
        )
        self.control = ft.Container(
            content=ft.Row(
                [
                    ft.Container(ft.Column([
                        titulo_panel("Shorts 9:16",
                                     ft.IconButton(ft.Icons.ADD, icon_size=16, on_click=self._nuevo,
                                                   tooltip="Nuevo Short: rango I–O o 30 s desde el cabezal"),
                                     ft.IconButton(ft.Icons.FOLDER_OPEN, icon_size=16, on_click=self._carpeta,
                                                   tooltip="Abrir la carpeta de Shorts")),
                        self.lista,
                        ft.TextButton("Renderizar pendientes", icon=ft.Icons.MOVIE_FILTER,
                                      on_click=lambda _: self._renderizar(None)),
                    ], spacing=4, expand=True), width=220),
                    ft.Column([
                        ft.Container(self.vista, bgcolor="#000000", alignment=ft.Alignment.CENTER, expand=True),
                        ft.Row([self.tiempo, self.tiempo_texto], spacing=4),
                    ], expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(self.detalle, width=240),
                ],
                spacing=8, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            bgcolor=TEMA.panel, padding=6, expand=True,
        )

    # --- Redibujado ------------------------------------------------------------------

    def refrescar(self) -> None:
        if self.app.sesion.estado.espacio_trabajo != "shorts":
            return
        capitulo = self.app.sesion.capitulo
        lista = sorted(capitulo.shorts.values(), key=lambda s: s.inicio)
        if self.id_short not in capitulo.shorts:
            self.id_short = lista[0].id if lista else None
        filas: list[ft.Control] = []
        for short in lista:
            icono, color = ICONOS_ESTADO[ctl.estado(self.app.sesion, short.id)]
            filas.append(ft.ListTile(
                dense=True, selected=short.id == self.id_short,
                leading=ft.Icon(icono, size=16, color=getattr(TEMA, color)),
                title=ft.Text(short.nombre, size=12),
                subtitle=ft.Text(f"{timecode.formatear(short.inicio)} · {timecode.duracion(short.duracion)}",
                                 size=10, color=TEMA.texto_suave),
                on_click=lambda _, i=short.id: self._elegir(i),
            ))
        self.lista.controls = filas or [texto_suave("Sin Shorts. Marque I–O en la timeline y pulse +.")]
        self.detalle.disabled = self.id_short is None
        if self.id_short is None:
            self.estado.value = self.info.value = ""
            return
        short = capitulo.shorts[self.id_short]
        if not self._editando:
            self.nombre.value = short.nombre
        cabezal = self.app.sesion.estado.cabezal
        self.tiempo.max = max(1, short.duracion - 1)
        self.tiempo.value = min(max(0, cabezal - short.inicio), short.duracion - 1)
        self.tiempo_texto.value = timecode.formatear(short.inicio + int(self.tiempo.value))
        animado = short.ventana.animacion.tiene("x") or short.ventana.animacion.tiene("zoom")
        self.info.value = (f"{timecode.formatear(short.inicio)} – {timecode.formatear(short.fin)}"
                           f" · {timecode.duracion(short.duracion)}" + (" · con keyframes" if animado else ""))
        if not self._arrastrando:
            x, zoom = ctl.ventana_en_cabezal(self.app.sesion, self.id_short)
            self.zoom.value = round(zoom, 2)
            self.x.max = LIENZO.ancho - LIENZO.ventana_vertical(0, zoom).ancho
            self.x.value = min(max(0.0, x), self.x.max)
        self.estado.value = f"Render: {ctl.estado(self.app.sesion, self.id_short)} · 720×1280, audio y subtítulos " \
                            f"del primer idioma"
        self._pedir_vista()

    def _pedir_vista(self) -> None:
        if self.id_short is None:
            return
        short = self.app.sesion.capitulo.shorts[self.id_short]
        f = short.inicio + int(self.tiempo.value or 0)

        def llegar(datos: bytes) -> None:
            self.vista.src = datos
            actualizar(self.vista)

        ctl.vista_vertical(self.app.sesion, self.id_short, f, float(self.x.value or 0), float(self.zoom.value or 1),
                           llegar)

    def encuadre(self):
        """Ventana vertical que muestra la vista (para dibujarla en el monitor 16:9)."""
        if self.id_short is None or self.id_short not in self.app.sesion.capitulo.shorts:
            return None
        return LIENZO.ventana_vertical(float(self.x.value or 0), float(self.zoom.value or 1))

    # --- Acciones ----------------------------------------------------------------------

    def _elegir(self, id_short: str) -> None:
        self.id_short = id_short
        short = self.app.sesion.capitulo.shorts[id_short]
        cabezal = self.app.sesion.estado.cabezal
        if not short.inicio <= cabezal < short.fin:
            self.app.sesion.ir_a(short.inicio)
        self.app.refrescar("shorts", "timeline", "monitor")

    def _nuevo(self, _evento) -> None:
        nuevo = ctl.crear(self.app.sesion, f"short-{len(self.app.sesion.capitulo.shorts) + 1}")
        if nuevo:
            self.id_short = nuevo

    def _mover_tiempo(self, evento) -> None:
        if self.id_short is None:
            return
        short = self.app.sesion.capitulo.shorts[self.id_short]
        self.app.sesion.ir_a(short.inicio + int(evento.control.value or 0))
        self.app.refrescar("shorts", "timeline", "monitor")

    def _previsualizar(self, _evento) -> None:
        self._arrastrando = True
        zoom = float(self.zoom.value or 1)
        self.x.max = LIENZO.ancho - LIENZO.ventana_vertical(0, zoom).ancho
        self.x.value = min(float(self.x.value or 0), self.x.max)
        self._pedir_vista()
        self.app.monitor.redibujar_superposicion()

    def _soltar_encuadre(self, _evento) -> None:
        self._arrastrando = False
        if self.id_short is not None:
            ctl.mover_ventana(self.app.sesion, self.id_short, float(self.x.value or 0), float(self.zoom.value or 1))

    def _keyframe(self, _evento) -> None:
        if self.id_short is not None:
            ctl.poner_keyframe(self.app.sesion, self.id_short, float(self.x.value or 0), float(self.zoom.value or 1))

    def _fija(self, _evento) -> None:
        if self.id_short is not None:
            ctl.quitar_keyframes(self.app.sesion, self.id_short)

    def _rango(self, _evento) -> None:
        if self.id_short is not None:
            ctl.usar_rango_io(self.app.sesion, self.id_short)

    def _ir_inicio(self, _evento) -> None:
        if self.id_short is not None:
            self.app.sesion.ir_a(self.app.sesion.capitulo.shorts[self.id_short].inicio)
            self.app.refrescar("shorts", "timeline", "monitor")

    def _editar(self, _evento) -> None:
        self._editando = True

    def _renombrar(self, _evento) -> None:
        self._editando = False
        if self.id_short is None:
            return
        short = self.app.sesion.capitulo.shorts.get(self.id_short)
        if short is not None and (self.nombre.value or "").strip() and self.nombre.value != short.nombre:
            ctl.renombrar(self.app.sesion, self.id_short, self.nombre.value or "")

    def _quitar(self, _evento) -> None:
        if self.id_short is not None and ctl.quitar(self.app.sesion, self.id_short):
            self.id_short = None

    def _renderizar_este(self, _evento) -> None:
        if self.id_short is not None:
            self._renderizar([self.id_short])

    def _renderizar(self, ids: list[str] | None) -> None:
        cantidad = ctl.renderizar(self.app.sesion, ids)
        self.app.aviso_breve(f"{cantidad} Short(s) en cola." if cantidad else "Todos los Shorts están al día.")

    def _carpeta(self, _evento) -> None:
        carpeta = carpeta_shorts(self.app.sesion.proyecto.raiz, self.app.sesion.capitulo.numero)
        carpeta.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(carpeta)])
        except OSError:
            pass
