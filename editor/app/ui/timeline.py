"""Timeline del minuto con capas y herramientas (E14, PROJECT.md 16.4 y 22.3).

Todo se dibuja en un `canvas` (solo lo visible); el cabezal es un contenedor
aparte para moverlo sin redibujar las capas. Los gestos se traducen a
comandos en `controladores/timeline.py`.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import flet as ft
import flet.canvas as cv

from editor.app.controladores import timeline as ctl
from editor.app.estado import ZOOMS
from editor.app.ui.tema import TEMA, texto_suave
from editor.app.ui.widgets import actualizar, timecode
from editor.core.comandos import CambiarEstadoCapa
from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO, FOTOGRAMAS_POR_MINUTO, FPS
from editor.core.modelo.capa import TipoCapa
from editor.core.modelo.marcador import clave_capa

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana

ALTO_REGLA = 24
ANCHO_CABECERA = 150
ICONOS_HERRAMIENTA = {
    "seleccion": (ft.Icons.NEAR_ME, "Selección (V)"),
    "cuchilla": (ft.Icons.CONTENT_CUT, "Cuchilla (C)"),
    "ripple": (ft.Icons.COMPARE_ARROWS, "Ripple (B)"),
    "roll": (ft.Icons.SWAP_HORIZ, "Roll (N)"),
    "slip": (ft.Icons.OPEN_WITH, "Slip (Y)"),
    "slide": (ft.Icons.HEIGHT, "Slide (U)"),
}
NOMBRES_ZOOM = {"capitulo": "Capítulo", "minuto": "Minuto", "segundos": "Segundos", "fotograma": "Fotograma"}


def _pintura(color: str, opacidad: float = 1.0, relleno: bool = True, grosor: float = 1.0) -> ft.Paint:
    return ft.Paint(color=ft.Colors.with_opacity(opacidad, color), stroke_width=grosor,
                    style=ft.PaintingStyle.FILL if relleno else ft.PaintingStyle.STROKE)


class Timeline:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self.alto_pista = 34
        self.ancho = 800.0
        self.pistas: list[ctl.Pista] = []
        self._arrastre: dict | None = None

        self.lienzo = cv.Canvas(shapes=[], height=ALTO_REGLA)
        self.cabezal = ft.Container(width=2, bgcolor=TEMA.cabezal, left=0, top=0, bottom=0)
        self.gestos = ft.GestureDetector(
            content=ft.Stack([self.lienzo, self.cabezal]),
            drag_interval=30,
            on_tap_down=self._tocar,
            on_double_tap_down=self._doble_toque,
            on_pan_start=self._empezar,
            on_pan_update=self._arrastrar,
            on_pan_end=self._soltar,
            on_scroll=self._rueda,
        )
        self.area = ft.Container(content=self.gestos, expand=True, on_size_change=self._redimensionar,
                                 size_change_interval=100)
        self.cabeceras = ft.Column(spacing=0, width=ANCHO_CABECERA)
        self.titulo = texto_suave("")
        self.botones_herramienta = {
            nombre: ft.IconButton(icono, tooltip=ayuda, icon_size=18, selected_icon_color=TEMA.acento,
                                  on_click=lambda _, n=nombre: self.app.elegir_herramienta(n))
            for nombre, (icono, ayuda) in ICONOS_HERRAMIENTA.items()
        }
        self.zoom = ft.Dropdown(
            width=130, dense=True, value=app.sesion.estado.zoom_timeline,
            options=[ft.DropdownOption(key=z, text=NOMBRES_ZOOM[z]) for z in ZOOMS], on_select=self._cambiar_zoom,
        )
        self.boton_iman = ft.IconButton(ft.Icons.LINK, tooltip="Imán", icon_size=18, selected=True,
                                        selected_icon_color=TEMA.acento, on_click=self._alternar_iman)
        self.capa_destino = ft.Dropdown(
            width=90, dense=True, label="Destino", value=app.sesion.estado.capa_destino,
            options=[ft.DropdownOption(key=c, text=c) for c in ctl.capas_de_tipo(TipoCapa.VIDEO)],
            on_select=self._cambiar_destino,
        )
        barra = ft.Row(
            [
                *self.botones_herramienta.values(),
                ft.VerticalDivider(width=8),
                self.boton_iman,
                ft.IconButton(ft.Icons.BOOKMARK_ADD, tooltip="Marcador en el cabezal", icon_size=18,
                              on_click=lambda _: self._marcador()),
                ft.IconButton(ft.Icons.TEXT_FIELDS, tooltip="Añadir texto en T1", icon_size=18,
                              on_click=lambda _: self._texto()),
                ft.IconButton(ft.Icons.CROP, tooltip="Quitar el rango I–O (Shift: extraer)", icon_size=18,
                              on_click=lambda _: self._quitar_rango()),
                self.capa_destino,
                ft.Checkbox(label="Global", value=app.sesion.estado.destino_global,
                            tooltip="Colocar en la pista Global del capítulo (música, logo fijo)",
                            on_change=self._cambiar_destino_global),
                ft.Container(expand=True),
                self.titulo,
                ft.IconButton(ft.Icons.ZOOM_OUT, tooltip="Pistas más bajas", icon_size=18,
                              on_click=lambda _: self._alto(-6)),
                ft.IconButton(ft.Icons.ZOOM_IN, tooltip="Pistas más altas", icon_size=18,
                              on_click=lambda _: self._alto(6)),
                self.zoom,
            ],
            spacing=0,
            height=40,
        )
        cuerpo = ft.Column(
            [ft.Row([self.cabeceras, self.area], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START)],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.control = ft.Container(
            content=ft.Column([barra, cuerpo], spacing=0, expand=True),
            bgcolor=TEMA.panel,
            padding=4,
            expand=True,
        )

    @property
    def sesion(self):
        return self.app.sesion

    def vista(self) -> ctl.Vista:
        return ctl.Vista.de(self.sesion, self.ancho)

    # --- Dibujo ------------------------------------------------------------------------

    def refrescar(self) -> None:
        sesion = self.sesion
        estado = sesion.estado
        self.pistas = ctl.pistas_visibles(sesion)
        vista = self.vista()
        for nombre, boton in self.botones_herramienta.items():
            boton.selected = nombre == estado.herramienta
        self.boton_iman.selected = estado.iman
        self.zoom.value = estado.zoom_timeline
        self.titulo.value = (f"{sesion.capitulo.codigo} · {timecode.formatear(vista.inicio)} – "
                             f"{timecode.formatear(min(vista.fin, FOTOGRAMAS_POR_CAPITULO))}")
        alto = ALTO_REGLA + len(self.pistas) * self.alto_pista
        self.lienzo.height = alto
        self.lienzo.width = self.ancho
        self.lienzo.shapes = self._regla(vista) + self._capas(vista)
        self._cabeceras()
        self.mover_cabezal()

    def mover_cabezal(self) -> None:
        vista = self.vista()
        x = vista.x(self.sesion.estado.cabezal)
        self.cabezal.visible = 0 <= x <= self.ancho
        self.cabezal.left = max(0.0, min(self.ancho - 2, x))

    def necesita_redibujo_por_cabezal(self) -> bool:
        """Con 'seguir al cabezal', al salir de lo visible se cambia la vista."""
        estado = self.sesion.estado
        if not estado.seguir_cabezal:
            return False
        vista = self.vista()
        if vista.inicio <= estado.cabezal < vista.fin:
            return False
        if estado.zoom_timeline in ("segundos", "fotograma"):
            estado.desplazamiento_timeline = max(0, estado.cabezal - vista.fotogramas // 10)
        return True

    def _regla(self, vista: ctl.Vista) -> list[cv.Shape]:
        formas: list[cv.Shape] = [cv.Rect(0, 0, self.ancho, ALTO_REGLA, paint=_pintura(TEMA.panel_alto))]
        if vista.fotogramas >= FOTOGRAMAS_POR_CAPITULO:
            paso, etiqueta = FOTOGRAMAS_POR_MINUTO, lambda f: f"{f // FOTOGRAMAS_POR_MINUTO:02d}"
        elif vista.fotogramas >= FOTOGRAMAS_POR_MINUTO:
            paso, etiqueta = 5 * FPS, lambda f: timecode.formatear(f)[:5]
        elif vista.fotogramas > 2 * FPS:
            paso, etiqueta = FPS, lambda f: timecode.formatear(f)[:5]
        else:
            paso, etiqueta = 1, lambda f: f"{f % FPS:02d}"
        estilo = ft.TextStyle(size=10, color=TEMA.texto_suave)
        primero = (vista.inicio // paso) * paso
        for f in range(primero, vista.fin + 1, paso):
            x = vista.x(f)
            if 0 <= x <= self.ancho:
                formas.append(cv.Line(x, ALTO_REGLA - 8, x, ALTO_REGLA, paint=_pintura(TEMA.texto_suave, grosor=1)))
                formas.append(cv.Text(x + 2, 2, etiqueta(f), style=estilo))
        estado = self.sesion.estado
        if estado.entrada is not None or estado.salida is not None:
            x0 = vista.x(estado.entrada if estado.entrada is not None else vista.inicio)
            x1 = vista.x(estado.salida if estado.salida is not None else vista.fin)
            formas.append(cv.Rect(x0, 0, max(1.0, x1 - x0), ALTO_REGLA, paint=_pintura(TEMA.entrada_salida, 0.25)))
        for marcador in self.sesion.capitulo.marcadores_en_rango(vista.inicio, vista.fin):
            x = vista.x(marcador.f)
            formas.append(cv.Rect(x - 3, 0, 6, 10, paint=_pintura(TEMA.marcador)))
            if marcador.nombre:
                formas.append(cv.Text(x + 5, 0, marcador.nombre, style=ft.TextStyle(size=10, color=TEMA.marcador)))
        return formas

    def _capas(self, vista: ctl.Vista) -> list[cv.Shape]:
        sesion = self.sesion
        capitulo = sesion.capitulo
        estado = sesion.estado
        formas: list[cv.Shape] = []
        alto_total = len(self.pistas) * self.alto_pista
        # Fondo alterno de las pistas y separación de minutos.
        for i, _pista in enumerate(self.pistas):
            y = ALTO_REGLA + i * self.alto_pista
            formas.append(cv.Rect(0, y, self.ancho, self.alto_pista,
                                  paint=_pintura(TEMA.panel_alto if i % 2 else TEMA.panel)))
        for f in range((vista.inicio // FOTOGRAMAS_POR_MINUTO + 1) * FOTOGRAMAS_POR_MINUTO, vista.fin, FOTOGRAMAS_POR_MINUTO):
            x = vista.x(f)
            formas.append(cv.Line(x, ALTO_REGLA, x, ALTO_REGLA + alto_total, paint=_pintura(TEMA.borde, grosor=1)))
        x_fin = vista.x(FOTOGRAMAS_POR_CAPITULO)
        if x_fin < self.ancho:
            formas.append(cv.Rect(x_fin, ALTO_REGLA, self.ancho - x_fin, alto_total, paint=_pintura(TEMA.fuera_marco, 0.8)))
        minuto_visible = estado.minuto if estado.zoom_timeline == "minuto" else None
        estilo = ft.TextStyle(size=11, color=TEMA.texto)
        for i, pista in enumerate(self.pistas):
            y = ALTO_REGLA + i * self.alto_pista + 2
            alto = self.alto_pista - 4
            estado_capa = capitulo.capas.get(clave_capa(pista.capa.codigo, pista.en_global))
            color = TEMA.color_capa(pista.capa.tipo.value)
            for elemento in ctl.elementos_de_pista(sesion, pista, vista):
                x0 = max(-2.0, vista.x(elemento.inicio))
                x1 = min(self.ancho + 2, vista.x(elemento.fin))
                ancho = max(2.0, x1 - x0)
                opacidad = 1.0
                if estado_capa is not None and not estado_capa.visible:
                    opacidad = 0.4
                if elemento.estado.bloqueado or (estado_capa is not None and estado_capa.bloqueada):
                    opacidad *= 0.6
                if not elemento.estado.activo:
                    opacidad *= 0.5
                fantasma = (minuto_visible is not None and not elemento.en_global
                            and elemento.minuto_inicio != minuto_visible)
                if fantasma:
                    formas.append(cv.Rect(x0, y, ancho, alto, border_radius=3, paint=_pintura(TEMA.fantasma, 0.3)))
                    formas.append(cv.Rect(x0, y, ancho, alto, border_radius=3,
                                          paint=_pintura(TEMA.fantasma, 0.9, relleno=False)))
                else:
                    formas.append(cv.Rect(x0, y, ancho, alto, border_radius=3, paint=_pintura(color, opacidad)))
                if elemento.en_global:
                    formas.append(cv.Rect(x0, y, ancho, alto, border_radius=3,
                                          paint=_pintura(TEMA.global_borde, relleno=False, grosor=1.5)))
                if elemento.excede_fuente:
                    formas.append(cv.Rect(x0, y + alto - 3, ancho, 3, paint=_pintura(TEMA.error)))
                if elemento.id in estado.seleccion:
                    formas.append(cv.Rect(x0, y, ancho, alto, border_radius=3,
                                          paint=_pintura(TEMA.seleccion, relleno=False, grosor=2)))
                if ancho > 24:
                    formas.append(cv.Text(x0 + 4, y + 2, elemento.nombre, style=estilo, max_width=ancho - 8, max_lines=1,
                                          ellipsis="…"))
        return formas

    def _cabeceras(self) -> None:
        capitulo = self.sesion.capitulo
        filas: list[ft.Control] = [ft.Container(height=ALTO_REGLA)]
        for pista in self.pistas:
            clave = clave_capa(pista.capa.codigo, pista.en_global)
            estado = capitulo.capas.get(clave)
            visible = estado.visible if estado else True
            silenciada = estado.silenciada if estado else False
            bloqueada = estado.bloqueada if estado else False
            solo = estado.solo if estado else False
            controles: list[ft.Control] = [
                ft.Text(pista.etiqueta, size=11, width=34, color=TEMA.global_borde if pista.en_global else TEMA.texto),
            ]
            if pista.capa.tipo is TipoCapa.AUDIO:
                controles.append(self._icono(ft.Icons.VOLUME_OFF if silenciada else ft.Icons.VOLUME_UP, "Silenciar",
                                             clave, silenciada=not silenciada))
                controles.append(self._icono(ft.Icons.HEADSET if solo else ft.Icons.HEADSET_OFF, "Solo",
                                             clave, solo=not solo))
                idioma = estado.idioma if estado else ""
                controles.append(ft.TextButton(idioma or "*", tooltip="Idioma de la pista (* = común a todos)",
                                               on_click=lambda _, c=clave, i=idioma: self._rotar_idioma(c, i)))
            else:
                controles.append(self._icono(ft.Icons.VISIBILITY if visible else ft.Icons.VISIBILITY_OFF, "Ver",
                                             clave, visible=not visible))
            controles.append(self._icono(ft.Icons.LOCK if bloqueada else ft.Icons.LOCK_OPEN, "Bloquear",
                                         clave, bloqueada=not bloqueada))
            filas.append(ft.Container(ft.Row(controles, spacing=0), height=self.alto_pista,
                                      padding=ft.Padding.only(left=4)))
        self.cabeceras.controls = filas

    def _icono(self, icono, ayuda: str, clave: str, **cambios) -> ft.IconButton:
        return ft.IconButton(icono, tooltip=ayuda, icon_size=14, width=26, height=26, padding=0,
                             on_click=lambda _: self._estado_capa(clave, **cambios))

    def _estado_capa(self, clave: str, **cambios) -> None:
        if self.sesion.ejecutar(lambda: CambiarEstadoCapa(self.sesion.estado.capitulo, clave, **cambios)):
            self.app.refrescar("timeline", "monitor")

    def _rotar_idioma(self, clave: str, actual: str) -> None:
        opciones = [""] + list(self.sesion.proyecto.idiomas)
        siguiente = opciones[(opciones.index(actual) + 1) % len(opciones)] if actual in opciones else ""
        self._estado_capa(clave, idioma=siguiente)

    # --- Gestos ------------------------------------------------------------------------

    def _redimensionar(self, evento: ft.LayoutSizeChangeEvent) -> None:
        if abs(evento.width - self.ancho) > 1:
            self.ancho = max(100.0, evento.width)
            self.refrescar()
            actualizar(self.control)

    def _pista_en(self, y: float) -> ctl.Pista | None:
        indice = int((y - ALTO_REGLA) // self.alto_pista)
        return self.pistas[indice] if y >= ALTO_REGLA and 0 <= indice < len(self.pistas) else None

    def _elemento_en(self, x: float, y: float):
        pista = self._pista_en(y)
        if pista is None:
            return None
        vista = self.vista()
        f = vista.f(x)
        tolerancia = ctl.BORDE_RECORTE_PX / vista.px_por_fotograma()
        for elemento in ctl.elementos_de_pista(self.sesion, pista, vista):
            if elemento.inicio - tolerancia <= f < elemento.fin + tolerancia:
                return elemento
        return None

    def _tocar(self, evento: ft.TapEvent) -> None:
        self.app.enfocar("timeline")
        if evento.local_position is None:
            return
        x, y = evento.local_position.x, evento.local_position.y
        vista = self.vista()
        f = max(0, min(FOTOGRAMAS_POR_CAPITULO - 1, vista.f(x)))
        if y < ALTO_REGLA:                 # la regla solo mueve el cabezal
            self.app.mover_cabezal_a(f)
            return
        elemento = self._elemento_en(x, y)
        if elemento is None:
            if not self.app.shift_presionado:
                self.app.seleccionar(set(), refrescar=False)
            self.app.mover_cabezal_a(f)
            return
        if self.sesion.estado.herramienta == "cuchilla":
            if ctl.cortar_en(self.sesion, ctl.iman(self.sesion, vista, f, set()), elemento.id):
                self.app.refrescar("timeline", "monitor")
            return
        if self.app.shift_presionado:
            self.app.seleccionar(self.sesion.estado.seleccion ^ {elemento.id})
        else:
            self.app.seleccionar({elemento.id})

    def _doble_toque(self, evento: ft.TapEvent) -> None:
        """Doble clic en un Elemento: ir a su Pieza en el Taller."""
        if evento.local_position is None:
            return
        elemento = self._elemento_en(evento.local_position.x, evento.local_position.y)
        if elemento is not None and elemento.fuente.ref in self.sesion.proyecto.taller.piezas:
            self.app.abrir_pieza(elemento.fuente.ref)

    def _empezar(self, evento: ft.DragStartEvent) -> None:
        x, y = evento.local_position.x, evento.local_position.y
        vista = self.vista()
        elemento = None if y < ALTO_REGLA else self._elemento_en(x, y)
        if elemento is None or self.sesion.estado.herramienta == "cuchilla" or not self.sesion.capitulo.editable(elemento):
            self._arrastre = {"tipo": "cabezal"}
            self.app.mover_cabezal_a(vista.f(x))
            return
        # Flutter también inicia un arrastre en un clic simple: con Shift la selección
        # ya la decidió el toque (sumar o quitar) y aquí no se toca.
        if elemento.id not in self.sesion.estado.seleccion and not self.app.shift_presionado:
            self.app.seleccionar({elemento.id}, refrescar=False)
        self._arrastre = {
            "tipo": "elemento", "id": elemento.id, "original": copy.deepcopy(elemento),
            "zona": ctl.zona_de(elemento, vista, x), "x0": x, "vista": vista,
            # Sin desplazamiento no se ejecuta nada (un clic no deja pasos vacíos en el historial).
            "ultimo_delta": (0, self._pista_en(y)),
        }

    def _arrastrar(self, evento: ft.DragUpdateEvent) -> None:
        arrastre = self._arrastre
        if arrastre is None or evento.local_position is None:
            return
        x, y = evento.local_position.x, evento.local_position.y
        if arrastre["tipo"] == "cabezal":
            self.app.mover_cabezal_a(self.vista().f(x))
            return
        vista: ctl.Vista = arrastre["vista"]
        delta = round((x - arrastre["x0"]) / vista.px_por_fotograma())
        pista = self._pista_en(y)
        if (delta, pista) == arrastre["ultimo_delta"]:
            return
        arrastre["ultimo_delta"] = (delta, pista)
        elemento = self.sesion.capitulo.buscar(arrastre["id"])
        if elemento is None:
            return
        antes = self.sesion.avisar
        self.sesion.avisar = self.app.aviso_breve   # los choques al arrastrar no abren diálogos
        try:
            ctl.arrastrar(self.sesion, elemento, arrastre["zona"], arrastre["original"], delta, vista, pista)
        finally:
            self.sesion.avisar = antes
        self.refrescar()
        actualizar(self.control)

    def _soltar(self, _evento) -> None:
        arrastre, self._arrastre = self._arrastre, None
        if arrastre is not None and arrastre["tipo"] == "elemento":
            self.app.refrescar("timeline", "monitor", "inspector", "mapa")

    def _rueda(self, evento: ft.ScrollEvent) -> None:
        if evento.scroll_delta is None:
            return
        estado = self.sesion.estado
        paso = 1 if (evento.scroll_delta.y or evento.scroll_delta.x) > 0 else -1
        if self.app.ctrl_presionado:
            self.app.cambiar_zoom_timeline(-paso)
            return
        if estado.zoom_timeline in ("segundos", "fotograma"):
            visibles = ctl.FOTOGRAMAS_VISIBLES[estado.zoom_timeline]
            estado.desplazamiento_timeline = max(0, min(FOTOGRAMAS_POR_CAPITULO - visibles,
                                                        estado.desplazamiento_timeline + paso * visibles // 8))
            self.refrescar()
            actualizar(self.control)

    # --- Barra -------------------------------------------------------------------------

    def _cambiar_zoom(self, evento) -> None:
        self.app.cambiar_zoom_timeline(nombre=evento.control.value)

    def _alternar_iman(self, _evento) -> None:
        self.sesion.estado.iman = not self.sesion.estado.iman
        self.refrescar()

    def _cambiar_destino(self, evento) -> None:
        self.sesion.estado.capa_destino = evento.control.value

    def _cambiar_destino_global(self, evento) -> None:
        self.sesion.estado.destino_global = bool(evento.control.value)

    def _alto(self, delta: int) -> None:
        self.alto_pista = max(22, min(80, self.alto_pista + delta))
        self.refrescar()

    def _marcador(self) -> None:
        if ctl.poner_marcador(self.sesion):
            self.refrescar()

    def _texto(self) -> None:
        if ctl.agregar_texto(self.sesion):
            self.app.refrescar("timeline", "monitor", "inspector")

    def _quitar_rango(self) -> None:
        if ctl.quitar_rango(self.sesion, extraer=self.app.shift_presionado):
            self.app.refrescar("timeline", "monitor", "mapa")
