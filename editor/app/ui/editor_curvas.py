"""Editor de curvas de keyframes.

Dibuja el valor de una propiedad a lo largo del Elemento, con sus keyframes.
Clic en un rombo: elegirlo; arrastrarlo en horizontal: moverlo en el tiempo
(`MoverKeyframe`). La curva del tramo que empieza en el keyframe elegido se
cambia con el selector; "bezier" habilita sus dos puntos de control.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft
import flet.canvas as cv

from editor.app.ui.tema import TEMA, texto_suave
from editor.app.ui.widgets import actualizar
from editor.core.comandos import MoverKeyframe, PonerKeyframe
from editor.core.modelo.keyframe import Keyframe
from editor.core.utiles.interpolacion import BEZIER, CONTROLES_PREDEFINIDOS, NOMBRES_CURVAS

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana

ALTO = 140
MARGEN = 10
RADIO = 5


class EditorCurvas:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self.propiedad: str | None = None
        self.indice_efecto: int | None = None   # None = propiedad del Elemento; si no, parámetro de ese efecto
        self.elegido: int | None = None     # f local del keyframe elegido
        self.ancho = 280.0
        self._arrastre: dict | None = None
        self.lienzo = cv.Canvas(shapes=[], height=ALTO, expand=True)
        self.area = ft.Container(
            content=ft.GestureDetector(content=self.lienzo, on_tap_down=self._tocar, on_pan_start=self._empezar,
                                       on_pan_update=self._arrastrar, on_pan_end=self._soltar, drag_interval=30),
            height=ALTO, bgcolor=TEMA.panel_alto, border_radius=4,
            on_size_change=self._redimensionar, size_change_interval=100,
        )
        self.curva = ft.Dropdown(dense=True, width=150, label="Curva",
                                 options=[ft.DropdownOption(key=c, text=c) for c in NOMBRES_CURVAS],
                                 on_select=self._cambiar_curva)
        self.controles = [
            ft.Slider(min=0, max=1, value=v, width=110, on_change_end=self._cambiar_controles)
            for v in CONTROLES_PREDEFINIDOS.get("ease-in-out", (0.42, 0.0, 0.58, 1.0))
        ]
        self.titulo = texto_suave("Curvas: elija una propiedad con keyframes en el inspector.")
        self.control = ft.Column(
            [self.titulo, self.area, ft.Row([self.curva]),
             ft.Row([texto_suave("P1"), self.controles[0], self.controles[1]], wrap=True),
             ft.Row([texto_suave("P2"), self.controles[2], self.controles[3]], wrap=True)],
            spacing=4,
        )

    def mostrar(self, propiedad: str | None, indice_efecto: int | None = None) -> None:
        if (propiedad, indice_efecto) != (self.propiedad, self.indice_efecto):
            self.propiedad = propiedad
            self.indice_efecto = indice_efecto
            self.elegido = None
        self.refrescar()

    # --- Datos -------------------------------------------------------------------------

    def _pista(self):
        elemento = self.app.sesion.seleccionado()
        if elemento is None or self.propiedad is None:
            return elemento, None
        if self.indice_efecto is not None:
            if self.indice_efecto >= len(elemento.efectos):
                return elemento, None
            animacion = elemento.efectos[self.indice_efecto].animacion
        else:
            animacion = elemento.animacion
        if not animacion.tiene(self.propiedad):
            return elemento, None
        return elemento, animacion.pista(self.propiedad)

    def _escalas(self, elemento, pista):
        valores = [k.valor for k in pista] or [0.0]
        minimo, maximo = min(valores), max(valores)
        if maximo - minimo < 1e-6:
            minimo, maximo = minimo - 1, maximo + 1
        duracion = max(1, elemento.duracion - 1)
        ancho_util = max(1.0, self.ancho - 2 * MARGEN)
        a_x = lambda f: MARGEN + f / duracion * ancho_util  # noqa: E731
        a_y = lambda v: ALTO - MARGEN - (v - minimo) / (maximo - minimo) * (ALTO - 2 * MARGEN)  # noqa: E731
        de_x = lambda x: round((x - MARGEN) / ancho_util * duracion)  # noqa: E731
        return a_x, a_y, de_x

    # --- Dibujo ------------------------------------------------------------------------

    def refrescar(self) -> None:
        elemento, pista = self._pista()
        formas: list[cv.Shape] = []
        habilitado = pista is not None and not pista.vacia
        self.curva.disabled = not habilitado or self.elegido is None
        for control in self.controles:
            control.disabled = True
        if not habilitado:
            self.titulo.value = "Curvas: elija una propiedad con keyframes en el inspector."
            self.lienzo.shapes = formas
            return
        donde = f"efecto {self.indice_efecto + 1} · " if self.indice_efecto is not None else ""
        self.titulo.value = f"Curvas · {donde}{self.propiedad} · {len(pista)} keyframes"
        a_x, a_y, _ = self._escalas(elemento, pista)
        linea = ft.Paint(color=TEMA.acento, stroke_width=2, style=ft.PaintingStyle.STROKE)
        puntos = max(2, int(self.ancho // 3))
        anterior = None
        for i in range(puntos + 1):
            f = (elemento.duracion - 1) * i / puntos
            p = (a_x(f), a_y(pista.valor_en(f, 0.0)))
            if anterior is not None:
                formas.append(cv.Line(anterior[0], anterior[1], p[0], p[1], paint=linea))
            anterior = p
        f_cabezal = self.app.sesion.estado.cabezal - elemento.inicio
        if 0 <= f_cabezal < elemento.duracion:
            x = a_x(f_cabezal)
            formas.append(cv.Line(x, 0, x, ALTO, paint=ft.Paint(color=TEMA.cabezal, stroke_width=1)))
        for keyframe in pista:
            x, y = a_x(keyframe.f), a_y(keyframe.valor)
            color = TEMA.seleccion if keyframe.f == self.elegido else TEMA.marcador
            formas.append(cv.Path([cv.Path.MoveTo(x, y - RADIO), cv.Path.LineTo(x + RADIO, y),
                                   cv.Path.LineTo(x, y + RADIO), cv.Path.LineTo(x - RADIO, y), cv.Path.Close()],
                                  paint=ft.Paint(color=color, style=ft.PaintingStyle.FILL)))
        self.lienzo.shapes = formas
        elegido = pista.obtener(self.elegido) if self.elegido is not None else None
        if elegido is not None:
            self.curva.value = elegido.curva
            controles = elegido.controles or CONTROLES_PREDEFINIDOS.get(elegido.curva, (0.42, 0.0, 0.58, 1.0))
            for control, valor in zip(self.controles, controles):
                control.value = max(0.0, min(1.0, valor))
                control.disabled = elegido.curva != BEZIER

    # --- Gestos ------------------------------------------------------------------------

    def _redimensionar(self, evento: ft.LayoutSizeChangeEvent) -> None:
        self.ancho = max(80.0, evento.width)
        self.refrescar()
        actualizar(self.lienzo)

    def _keyframe_en(self, x: float, y: float):
        elemento, pista = self._pista()
        if pista is None:
            return None
        a_x, a_y, _ = self._escalas(elemento, pista)
        for keyframe in pista:
            if abs(a_x(keyframe.f) - x) <= RADIO + 3 and abs(a_y(keyframe.valor) - y) <= RADIO + 6:
                return keyframe
        return None

    def _tocar(self, evento: ft.TapEvent) -> None:
        if evento.local_position is None:
            return
        keyframe = self._keyframe_en(evento.local_position.x, evento.local_position.y)
        self.elegido = keyframe.f if keyframe is not None else None
        self.refrescar()
        actualizar(self.control)

    def _empezar(self, evento: ft.DragStartEvent) -> None:
        keyframe = self._keyframe_en(evento.local_position.x, evento.local_position.y)
        if keyframe is not None:
            self.elegido = keyframe.f
            self._arrastre = {"origen": keyframe.f, "destino": keyframe.f}

    def _arrastrar(self, evento: ft.DragUpdateEvent) -> None:
        if self._arrastre is None or evento.local_position is None:
            return
        elemento, pista = self._pista()
        if pista is None:
            return
        _, _, de_x = self._escalas(elemento, pista)
        self._arrastre["destino"] = max(0, min(elemento.duracion - 1, de_x(evento.local_position.x)))

    def _soltar(self, _evento) -> None:
        arrastre, self._arrastre = self._arrastre, None
        elemento, _ = self._pista()
        if arrastre is None or elemento is None or arrastre["origen"] == arrastre["destino"]:
            return
        sesion = self.app.sesion
        if sesion.ejecutar(lambda: MoverKeyframe(sesion.estado.capitulo, elemento.id, self.propiedad,
                                                 arrastre["origen"], arrastre["destino"], self.indice_efecto)):
            self.elegido = arrastre["destino"]
            self.app.refrescar("inspector", "monitor")

    def _poner(self, curva: str, controles) -> None:
        elemento, pista = self._pista()
        if pista is None or self.elegido is None:
            return
        actual = pista.obtener(self.elegido)
        if actual is None:
            return
        sesion = self.app.sesion
        nuevo = Keyframe(actual.f, actual.valor, curva, tuple(controles) if curva == BEZIER else None)
        if sesion.ejecutar(lambda: PonerKeyframe(sesion.estado.capitulo, elemento.id, self.propiedad, nuevo,
                                                 self.indice_efecto)):
            self.app.refrescar("inspector", "monitor")

    def _cambiar_curva(self, evento) -> None:
        curva = evento.control.value
        self._poner(curva, CONTROLES_PREDEFINIDOS.get(curva, [c.value for c in self.controles]))

    def _cambiar_controles(self, _evento) -> None:
        self._poner(BEZIER, [float(c.value or 0) for c in self.controles])
