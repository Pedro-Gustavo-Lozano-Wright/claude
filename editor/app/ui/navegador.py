"""Árbol Proyecto → Capítulos → Minutos, Brutos y Taller (E12, T12.5).

Los capítulos se cargan al elegirlos (carga perezosa del proyecto); los
minutos muestran los mismos dos ejes de estado que el mapa.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from editor.app.controladores import proyecto as ctl_proyecto
from editor.app.controladores import taller as ctl_taller
from editor.app.ui.tema import TEMA, texto, texto_suave, titulo_panel
from editor.app.ui.widgets import timecode
from editor.core.comandos import CambiarTituloCapitulo
from editor.core.modelo.bruto import TipoMedio
from editor.core.modelo.minuto import EstadoTrabajo
from editor.core.tiempo.granularidad import texto_fps

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana

ICONO_TIPO = {TipoMedio.VIDEO: ft.Icons.MOVIE, TipoMedio.AUDIO: ft.Icons.AUDIOTRACK, TipoMedio.IMAGEN: ft.Icons.IMAGE}
ICONO_TRABAJO = {
    EstadoTrabajo.VACIO: (ft.Icons.RADIO_BUTTON_UNCHECKED, "minuto_vacio"),
    EstadoTrabajo.EN_PROGRESO: (ft.Icons.CONTRAST, "minuto_progreso"),
    EstadoTrabajo.LISTO: (ft.Icons.CIRCLE, "minuto_listo"),
}


class Navegador:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self.capitulos = ft.Dropdown(dense=True, expand=True, on_select=self._elegir_capitulo)
        self.titulo_capitulo = ft.TextField(
            dense=True, hint_text="Título del capítulo", text_size=TEMA.tamano_texto,
            on_submit=self._titulo, on_blur=self._titulo_y_salir, on_focus=self._enfocar_titulo,
        )
        self._editando_titulo = False
        self.minutos = ft.Column(spacing=0)
        self.brutos = ft.Column(spacing=0)
        self.piezas = ft.Column(spacing=0)
        contenido = ft.Column(
            [
                titulo_panel("Proyecto",
                             ft.IconButton(ft.Icons.UPLOAD_FILE, tooltip="Importar Brutos", icon_size=18,
                                           on_click=self._importar),
                             ft.IconButton(ft.Icons.CREATE_NEW_FOLDER, tooltip="Nuevo capítulo", icon_size=18,
                                           on_click=lambda _: self._nuevo_capitulo())),
                texto(app.sesion.proyecto.nombre, weight=ft.FontWeight.BOLD),
                ft.Row([self.capitulos], spacing=0),
                self.titulo_capitulo,
                ft.ExpansionTile(title=texto("Minutos"), expanded=True, controls=[self.minutos],
                                 tile_padding=ft.Padding.symmetric(horizontal=4)),
                ft.ExpansionTile(title=texto("Brutos"), expanded=True, controls=[self.brutos],
                                 tile_padding=ft.Padding.symmetric(horizontal=4)),
                ft.ExpansionTile(title=texto("Taller · Piezas"), expanded=True, controls=[self.piezas],
                                 tile_padding=ft.Padding.symmetric(horizontal=4)),
            ],
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.control = ft.Container(content=contenido, bgcolor=TEMA.panel, padding=6, expand=True)

    @property
    def sesion(self):
        return self.app.sesion

    def refrescar(self) -> None:
        sesion = self.sesion
        proyecto = sesion.proyecto
        self.capitulos.options = [
            ft.DropdownOption(key=str(n), text=f"cap{n:04d}") for n in proyecto.numeros_capitulos()
        ]
        self.capitulos.value = str(sesion.estado.capitulo)
        capitulo = sesion.capitulo
        if not self._editando_titulo:
            self.titulo_capitulo.value = capitulo.titulo
        actual = sesion.estado.minuto
        self.minutos.controls = [
            ft.ListTile(
                dense=True,
                leading=ft.Icon(ICONO_TRABAJO[m.estado_trabajo][0], size=14,
                                color=getattr(TEMA, ICONO_TRABAJO[m.estado_trabajo][1])
                                if m.estado_trabajo is not EstadoTrabajo.VACIO else TEMA.texto_suave),
                title=ft.Text(f"{m.codigo} · {timecode.formatear(m.inicio)[:5]}", size=12,
                              weight=ft.FontWeight.BOLD if m.numero == actual else None),
                subtitle=ft.Text(m.notas, size=10, color=TEMA.texto_suave) if m.notas else None,
                selected=m.numero == actual,
                on_click=lambda _, n=m.numero: self.app.ir_a_minuto(n),
            )
            for m in capitulo.minutos
        ]
        taller = proyecto.taller
        self.brutos.controls = [self._fila_bruto(b) for b in sorted(taller.brutos.values(), key=lambda b: b.numero)] or [
            texto_suave("Sin Brutos. Importe archivos con ⬆.")]
        self.piezas.controls = [self._fila_pieza(p) for p in sorted(taller.piezas.values(), key=lambda p: p.numero)] or [
            texto_suave("Sin Piezas. Cree una desde un Bruto.")]

    def _fila_bruto(self, bruto) -> ft.Control:
        detalles = [bruto.tipo.value]
        if bruto.ancho:
            detalles.append(f"{bruto.ancho}×{bruto.alto}")
        if bruto.fps is not None:
            detalles.append(f"{texto_fps(bruto.fps)} fps")
        aviso = bruto.necesita_revision_fps
        acciones = []
        if bruto.tipo in (TipoMedio.IMAGEN, TipoMedio.AUDIO):
            acciones.append(ft.IconButton(ft.Icons.PLAYLIST_ADD, tooltip="Colocar en el cabezal", icon_size=16,
                                          on_click=lambda _, i=bruto.id: self._colocar_bruto(i)))
        return ft.ListTile(
            dense=True,
            leading=ft.Icon(ft.Icons.WARNING_AMBER if aviso else ICONO_TIPO.get(bruto.tipo, ft.Icons.MOVIE),
                            color=TEMA.error if aviso else TEMA.texto_suave, size=16),
            title=ft.Text(f"{bruto.numero:03d} {bruto.nombre}", size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            subtitle=ft.Text(" · ".join(detalles) + (" · revisar fps" if aviso else ""), size=10, color=TEMA.texto_suave),
            trailing=ft.Row(acciones, tight=True) if acciones else None,
            on_click=lambda _, i=bruto.id: self.app.abrir_bruto(i),
        )

    def _fila_pieza(self, pieza) -> ft.Control:
        if pieza.horneado is None:
            estado = "sin hornear"
        elif pieza.horneada_al_dia:
            estado = f"horneada v{pieza.version}"
        else:
            estado = f"receta cambiada (v{pieza.version})"
        return ft.ListTile(
            dense=True,
            leading=ft.Icon(ft.Icons.MOVIE_FILTER, size=16,
                            color=TEMA.render_al_dia if pieza.horneada_al_dia else TEMA.texto_suave),
            title=ft.Text(f"P{pieza.numero:03d} {pieza.nombre}", size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            subtitle=ft.Text(estado, size=10, color=TEMA.texto_suave),
            trailing=ft.IconButton(ft.Icons.PLAYLIST_ADD, tooltip="Colocar en el cabezal (capa destino)", icon_size=16,
                                   disabled=pieza.horneado is None,
                                   on_click=lambda _, i=pieza.id: self._colocar_pieza(i)),
            on_click=lambda _, i=pieza.id: self.app.abrir_pieza(i),
        )

    # --- Acciones ----------------------------------------------------------------------

    async def _importar(self, _evento) -> None:
        archivos = await self.app.selector.pick_files(dialog_title="Importar Brutos", allow_multiple=True)
        rutas = [archivo.path for archivo in archivos or [] if archivo.path]
        if rutas:
            from pathlib import Path

            from editor.app.controladores import medios

            medios.importar(self.sesion, [Path(r) for r in rutas])
            self.app.aviso_breve(f"Importando {len(rutas)} archivo(s)…")

    def _nuevo_capitulo(self) -> None:
        if self.sesion.solo_lectura:
            self.app.avisar("El proyecto está abierto en solo lectura.")
            return
        numero = ctl_proyecto.nuevo_capitulo(self.sesion)
        self.app.cambiar_capitulo(numero)

    def _elegir_capitulo(self, evento) -> None:
        if evento.control.value:
            self.app.cambiar_capitulo(int(evento.control.value))

    def _titulo(self, evento) -> None:
        valor = (evento.control.value or "").strip()
        if valor != self.sesion.capitulo.titulo:
            self.sesion.ejecutar(lambda: CambiarTituloCapitulo(self.sesion.estado.capitulo, valor))

    def _enfocar_titulo(self, _evento) -> None:
        self._editando_titulo = True
        self.app.enfocar("texto")

    def _titulo_y_salir(self, evento) -> None:
        self._editando_titulo = False
        self._titulo(evento)
        self.app.enfocar("timeline")

    def _colocar_pieza(self, id_pieza: str) -> None:
        if ctl_taller.colocar_pieza(self.sesion, id_pieza):
            self.app.refrescar("timeline", "monitor", "inspector", "mapa", "navegador")

    def _colocar_bruto(self, id_bruto: str) -> None:
        if ctl_taller.colocar_bruto(self.sesion, id_bruto):
            self.app.refrescar("timeline", "monitor", "inspector", "mapa", "navegador")
