"""Mapa de los 24 minutos con sus estados (E14, PROJECT.md 22.3).

Cada celda muestra dos ejes a la vez:
- relleno = trabajo (vacío / en progreso / listo);
- punto = render (sin render / desactualizado / al día);
- barra inferior = pre-render de reproducción listo (verde) o no (rojo oscuro).

Clic: ir al minuto. Clic derecho en dos celdas: intercambiar esos minutos.
Doble clic: marcar o desmarcar el minuto como listo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from editor.app.controladores import render as ctl_render
from editor.app.controladores import timeline as ctl_timeline
from editor.app.ui.tema import TEMA
from editor.core.comandos import MarcarMinuto
from editor.core.modelo.minuto import EstadoRender, EstadoTrabajo

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana

RELLENO = {
    EstadoTrabajo.VACIO: "minuto_vacio",
    EstadoTrabajo.EN_PROGRESO: "minuto_progreso",
    EstadoTrabajo.LISTO: "minuto_listo",
}
PUNTO = {
    EstadoRender.SIN_RENDER: None,
    EstadoRender.DESACTUALIZADO: "render_desactualizado",
    EstadoRender.AL_DIA: "render_al_dia",
}


class MapaCapitulo:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self._origen_intercambio: int | None = None
        self.fila = ft.Row(spacing=3, expand=True)
        self.control = ft.Container(content=self.fila, bgcolor=TEMA.panel, padding=4, expand=True)

    def refrescar(self) -> None:
        sesion = self.app.sesion
        capitulo = sesion.capitulo
        render = ctl_render.estados_de_render(sesion)
        prerender = sesion.vista_previa.minutos_listos(capitulo, sesion.estado.idioma_escucha)
        actual = sesion.estado.minuto
        celdas: list[ft.Control] = []
        for minuto in capitulo.minutos:
            n = minuto.numero
            punto = PUNTO[render.get(n, EstadoRender.SIN_RENDER)]
            borde = TEMA.seleccion if n == actual else (TEMA.marcador if n == self._origen_intercambio else TEMA.borde)
            celdas.append(ft.Container(
                content=ft.Stack([
                    ft.Container(ft.Text(f"{n:02d}", size=11, color=TEMA.texto), alignment=ft.Alignment.CENTER,
                                 expand=True),
                    ft.Container(width=7, height=7, border_radius=4, right=3, top=3,
                                 bgcolor=getattr(TEMA, punto) if punto else None),
                    ft.Container(height=3, left=0, right=0, bottom=0,
                                 bgcolor=TEMA.prerender_listo if prerender.get(n) else TEMA.prerender_falta),
                ], expand=True),
                bgcolor=getattr(TEMA, RELLENO[minuto.estado_trabajo]),
                border=ft.Border.all(2 if n == actual else 1, borde),
                border_radius=4,
                expand=True,
                tooltip=self._ayuda(minuto, render.get(n), prerender.get(n)),
                on_click=lambda _, m=n: self._ir(m),
                data=n,
            ))
            # Clic derecho y doble clic: el Container no los tiene; se envuelve en un detector.
            celdas[-1] = ft.GestureDetector(content=celdas[-1], expand=True,
                                            on_secondary_tap=lambda _, m=n: self._intercambiar(m),
                                            on_double_tap=lambda _, m=n: self._marcar_listo(m))
        self.fila.controls = celdas

    @staticmethod
    def _ayuda(minuto, render, prerender) -> str:
        trabajo = {EstadoTrabajo.VACIO: "vacío", EstadoTrabajo.EN_PROGRESO: "en progreso",
                   EstadoTrabajo.LISTO: "listo"}[minuto.estado_trabajo]
        estado_render = {EstadoRender.SIN_RENDER: "sin render", EstadoRender.DESACTUALIZADO: "render desactualizado",
                         EstadoRender.AL_DIA: "render al día", None: "sin render"}[render]
        vista = "vista previa lista" if prerender else "vista previa pendiente"
        notas = f"\n{minuto.notas}" if minuto.notas else ""
        return f"{minuto.codigo}: {trabajo} · {estado_render} · {vista}{notas}"

    def _ir(self, minuto: int) -> None:
        self.app.ir_a_minuto(minuto)

    def _marcar_listo(self, minuto: int) -> None:
        sesion = self.app.sesion
        listo = not sesion.capitulo.minuto(minuto).listo
        if sesion.ejecutar(lambda: MarcarMinuto(sesion.estado.capitulo, minuto, listo=listo)):
            self.app.refrescar("mapa", "navegador")

    def _intercambiar(self, minuto: int) -> None:
        if self._origen_intercambio is None:
            self._origen_intercambio = minuto
            self.app.aviso_breve(f"Clic derecho en otro minuto para intercambiarlo con min{minuto:02d}.")
            self.app.refrescar("mapa")
            return
        origen, self._origen_intercambio = self._origen_intercambio, None
        if origen == minuto:
            self.app.refrescar("mapa")
            return

        def confirmar() -> None:
            if ctl_timeline.intercambiar_minutos(self.app.sesion, origen, minuto):
                self.app.refrescar("timeline", "monitor", "mapa", "navegador")

        cantidad = sum(1 for e in self.app.sesion.capitulo.elementos_de_minutos()
                       if e.minuto_inicio in (origen, minuto))
        self.app.confirmar(
            "Intercambiar minutos",
            f"Se intercambiarán min{origen:02d} y min{minuto:02d}: {cantidad} archivos se renombrarán al guardar.",
            confirmar,
        )
        self.app.refrescar("mapa")
