"""Tareas de fondo y renders (básico; perfiles y exportación completa en E21).

- `BarraTareas`: franja inferior de la ventana con la tarea en curso, su
  progreso y cuántas quedan; siempre visible.
- `ColaRender`: panel del espacio Render: renderizar el minuto, el rango I–O
  (en minutos) o el capítulo, en pistas o un archivo por idioma, y la lista
  de entregables del capítulo.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import flet as ft

from editor.app.controladores import render as ctl_render
from editor.app.ui.tema import TEMA, texto_suave, titulo_panel
from editor.core.eventos import TareaProgreso, TareaTerminada
from editor.core.tiempo.granularidad import minuto_de
from editor.core.tiempo.nomenclatura import carpeta_render

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana


class BarraTareas:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self.tareas: dict[str, tuple[str, float]] = {}   # id → (descripción, fracción)
        self.texto = texto_suave("")
        self.progreso = ft.ProgressBar(value=0, width=180, visible=False, color=TEMA.acento, bgcolor=TEMA.borde)
        self.cancelar = ft.IconButton(ft.Icons.CLOSE, icon_size=14, width=24, height=24, visible=False,
                                      tooltip="Cancelar la tarea", on_click=self._cancelar)
        self.mensaje = texto_suave("")
        self.control = ft.Container(
            content=ft.Row([self.progreso, self.texto, self.cancelar, ft.Container(expand=True), self.mensaje],
                           spacing=8, height=22),
            bgcolor=TEMA.panel_alto,
            padding=ft.Padding.symmetric(horizontal=8),
        )
        app.escuchar(TareaProgreso, self._progreso)
        app.escuchar(TareaTerminada, self._terminada)

    # Las tareas del monitor son continuas y cortas: no se listan.
    OCULTAS = frozenset({"monitor", "visor"})

    def _progreso(self, evento: TareaProgreso) -> None:
        if evento.tipo in self.OCULTAS:
            return
        self.tareas[evento.id_tarea] = (evento.descripcion or evento.tipo, evento.fraccion)
        self.app.refrescar("tareas")

    def _terminada(self, evento: TareaTerminada) -> None:
        if evento.tipo in self.OCULTAS:
            return
        self.tareas.pop(evento.id_tarea, None)
        if not evento.exito and evento.mensaje:
            self.mensaje.value = f"Falló {evento.tipo}: {evento.mensaje}"
        self.app.refrescar("tareas", "mapa", "navegador", "taller", "render")

    def refrescar(self) -> None:
        if not self.tareas:
            self.progreso.visible = self.cancelar.visible = False
            self.texto.value = "Sin tareas en curso"
            return
        id_tarea, (descripcion, fraccion) = next(iter(self.tareas.items()))
        self.progreso.visible = self.cancelar.visible = True
        self.progreso.value = max(0.0, min(1.0, fraccion))
        self.cancelar.data = id_tarea
        resto = len(self.tareas) - 1
        self.texto.value = f"{descripcion} {round(fraccion * 100)} %" + (f" · y {resto} más" if resto else "")

    def _cancelar(self, evento) -> None:
        if evento.control.data:
            self.app.sesion.cola.cancelar(evento.control.data)


class ColaRender:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self.por_idioma = ft.Checkbox(label="Un archivo por idioma", value=False)
        self.normalizar = ft.Checkbox(label="Sonoridad −14 LUFS (YouTube)", value=True,
                                      tooltip="Cada pista de idioma a −14 LUFS integrados, pico ≤ −1 dBFS")
        self.sonoridad = texto_suave("")
        self.lista = ft.Column(spacing=0)
        self.control = ft.Container(
            content=ft.Column(
                [
                    titulo_panel("Render"),
                    ft.Row([
                        ft.FilledButton("Minuto actual", icon=ft.Icons.MOVIE, on_click=lambda _: self._minuto()),
                        ft.OutlinedButton("Rango I–O", on_click=lambda _: self._rango()),
                        ft.OutlinedButton("Capítulo completo", on_click=lambda _: self._capitulo()),
                        self.por_idioma,
                        self.normalizar,
                    ], wrap=True),
                    ft.Row([ft.TextButton("Medir sonoridad del minuto", icon=ft.Icons.EQUALIZER,
                                          on_click=lambda _: self._medir(False)),
                            ft.TextButton("…del capítulo", on_click=lambda _: self._medir(True)),
                            self.sonoridad], wrap=True),
                    texto_suave("Los minutos al día se reutilizan: solo se renderiza lo que cambió."),
                    ft.Divider(),
                    titulo_panel("Entregables del capítulo"),
                    self.lista,
                ],
                spacing=6, scroll=ft.ScrollMode.AUTO, expand=True,
            ),
            bgcolor=TEMA.panel,
            padding=6,
            expand=True,
        )

    def refrescar(self) -> None:
        sesion = self.app.sesion
        capitulo = sesion.capitulo
        carpeta = carpeta_render(sesion.proyecto.raiz, capitulo.numero)
        filas: list[ft.Control] = []
        for registro in sorted(capitulo.renders, key=lambda r: (r.nombre.desde is None, r.nombre.desde or 0,
                                                                 r.nombre.version)):
            ruta = carpeta / registro.nombre.archivo
            filas.append(ft.ListTile(
                dense=True,
                leading=ft.Icon(ft.Icons.MOVIE, size=16,
                                color=TEMA.render_al_dia if ruta.exists() else TEMA.error),
                title=ft.Text(registro.nombre.archivo, size=12),
                subtitle=ft.Text("en disco" if ruta.exists() else "falta el archivo", size=10, color=TEMA.texto_suave),
                trailing=ft.IconButton(ft.Icons.FOLDER_OPEN, icon_size=16, tooltip="Abrir la carpeta",
                                       on_click=lambda _, c=carpeta: _abrir_carpeta(c)),
            ))
        self.lista.controls = filas or [texto_suave("Todavía no hay renders de este capítulo.")]

    def _medir(self, capitulo: bool) -> None:
        from editor.app.controladores import audio as ctl_audio

        minuto = self.app.sesion.estado.minuto

        def listo(lufs: float, pico: float) -> None:
            self.sonoridad.value = ("Capítulo: " if capitulo else f"min{minuto:02d}: ") + _texto_sonoridad(lufs, pico)
            self.app.refrescar("render")

        ctl_audio.medir_sonoridad(self.app.sesion, None if capitulo else minuto, None if capitulo else minuto, listo)
        self.sonoridad.value = "Midiendo…"

    def _minuto(self) -> None:
        minuto = self.app.sesion.estado.minuto
        ctl_render.renderizar(self.app.sesion, minuto, minuto, self.por_idioma.value, self.normalizar.value)
        self.app.aviso_breve(f"Render del minuto {minuto:02d} en cola.")

    def _rango(self) -> None:
        estado = self.app.sesion.estado
        if estado.entrada is None or estado.salida is None:
            self.app.avisar("Marque entrada (I) y salida (O) en la timeline: se renderizan los minutos que cubren.")
            return
        desde, hasta = minuto_de(estado.entrada), min(23, minuto_de(max(estado.entrada, estado.salida - 1)))
        ctl_render.renderizar(self.app.sesion, desde, hasta, self.por_idioma.value, self.normalizar.value)
        self.app.aviso_breve(f"Render de los minutos {desde:02d}–{hasta:02d} en cola.")

    def _capitulo(self) -> None:
        ctl_render.renderizar(self.app.sesion, None, None, self.por_idioma.value, self.normalizar.value)
        self.app.aviso_breve("Render del capítulo completo en cola.")


def _texto_sonoridad(lufs: float, pico: float) -> str:
    if lufs == float("-inf"):
        return "Silencio."
    return f"{lufs:.1f} LUFS · pico {pico:.1f} dBFS" + ("  (YouTube: −14)" if abs(lufs + 14) > 1 else "  ✓")


def _abrir_carpeta(carpeta) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(["xdg-open", str(carpeta)])
    except OSError:
        pass
