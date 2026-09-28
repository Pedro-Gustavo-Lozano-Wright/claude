"""Propiedades del Elemento seleccionado, keyframes e historial.

Cada propiedad animable muestra su valor **en el cabezal**, un rombo (◆ hay
keyframe aquí, ◇ no) y flechas para saltar al keyframe anterior o siguiente.
Si la propiedad ya tiene keyframes, editar el valor pone un keyframe en el
cabezal; si no, cambia el valor base del Elemento.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import flet as ft

from editor.app.ui.editor_curvas import EditorCurvas
from editor.app.ui.tema import TEMA, texto, texto_suave, titulo_panel
from editor.app.ui.widgets import actualizar, timecode
from editor.core.comandos import (
    ActivarEfecto,
    AgregarEfecto,
    CambiarAGlobal,
    CambiarOpcionEfecto,
    CambiarParametroEfecto,
    CambiarPropiedad,
    CambiarVelocidad,
    PonerKeyframe,
    QuitarEfecto,
    QuitarKeyframe,
    ReordenarEfecto,
)
from editor.app.controladores import audio as ctl_audio
from editor.app.controladores import creativo as ctl_creativo
from editor.app.controladores import timeline as ctl_timeline
from editor.core.comandos.presets import ANIMACIONES_CLIP
from editor.core.modelo.efecto import descriptor_efecto, efecto_nuevo, tipos_efecto
from editor.core.modelo.transicion import DIRECCIONES, descriptor_transicion, tipos_transicion
from editor.core.espacio.transform import MODOS_MEZCLA
from editor.core.modelo.keyframe import Keyframe
from editor.core.modelo.texto import ALINEACIONES, ANIMACIONES_TEXTO, ETIQUETAS_ANIMACION
from editor.core.tiempo.nomenclatura import normalizar_nombre

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana

# propiedad → (etiqueta, a_pantalla, desde_pantalla, unidad)
ESPACIO = {
    "x": ("x", lambda v: v, lambda v: v, "px"),
    "y": ("y", lambda v: v, lambda v: v, "px"),
    "ancla_x": ("ancla x", lambda v: v, lambda v: v, "px"),
    "ancla_y": ("ancla y", lambda v: v, lambda v: v, "px"),
    "escala_x": ("escala x", lambda v: v * 100, lambda v: v / 100, "%"),
    "escala_y": ("escala y", lambda v: v * 100, lambda v: v / 100, "%"),
    "rotacion": ("rotación", lambda v: v, lambda v: v, "°"),
    "opacidad": ("opacidad", lambda v: v * 100, lambda v: max(0.0, min(1.0, v / 100)), "%"),
}
AUDIO = {
    "volumen": ("volumen", lambda v: v * 100, lambda v: max(0.0, min(2.0, v / 100)), "%"),
    "paneo": ("paneo", lambda v: v * 100, lambda v: max(-1.0, min(1.0, v / 100)), "%"),
}


class Inspector:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self.propiedad_activa = "x"
        self.curvas = EditorCurvas(app)
        self.cuerpo = ft.Column(spacing=4)
        self.historial = ft.Column(spacing=0)
        self.control = ft.Container(
            content=ft.Column(
                [titulo_panel("Inspector"), self.cuerpo, ft.Divider(), self.curvas.control, ft.Divider(),
                 titulo_panel("Historial"), self.historial],
                spacing=4, scroll=ft.ScrollMode.AUTO, expand=True,
            ),
            bgcolor=TEMA.panel,
            padding=6,
            expand=True,
        )

    @property
    def sesion(self):
        return self.app.sesion

    # --- Dibujo ------------------------------------------------------------------------

    def refrescar(self) -> None:
        self._historial()
        sesion = self.sesion
        seleccion = sesion.seleccionados()
        if not seleccion:
            self.cuerpo.controls = [texto_suave("Sin selección. Elija un Elemento en la timeline o en el monitor.")]
            self.curvas.mostrar(None)
            return
        if len(seleccion) > 1:
            self.cuerpo.controls = [texto(f"{len(seleccion)} Elementos seleccionados"),
                                    texto_suave("El inspector edita un Elemento a la vez.")]
            self.curvas.mostrar(None)
            return
        elemento = seleccion[0]
        f = sesion.estado.cabezal
        filas: list[ft.Control] = [
            self._campo_texto("nombre", elemento.nombre, lambda v: self._propiedad(elemento, "nombre", normalizar_nombre(v))),
            texto_suave(f"{'Global · ' if elemento.en_global else ''}{elemento.capa.codigo} · "
                        f"{timecode.formatear(elemento.inicio)} → {timecode.formatear(elemento.fin)} "
                        f"({timecode.duracion(elemento.duracion)})"),
            ft.Row([
                ft.Checkbox(label="Activo", value=elemento.estado.activo,
                            on_change=lambda e: self._propiedad(elemento, "estado.activo", bool(e.control.value))),
                ft.Checkbox(label="Bloqueado", value=elemento.estado.bloqueado,
                            on_change=lambda e: self._propiedad(elemento, "estado.bloqueado", bool(e.control.value))),
                ft.TextButton("Pasar a los minutos" if elemento.en_global else "Pasar a Global",
                              icon=ft.Icons.LAYERS,
                              tooltip="Global abarca varios minutos (música, logo fijo); los minutos, un tramo",
                              on_click=lambda _: self._ejecutar(lambda: CambiarAGlobal(
                                  self.sesion.estado.capitulo, elemento.id, not elemento.en_global))),
            ], wrap=True),
        ]
        if not elemento.es_texto:
            # Velocidad: con keyframes es una rampa (la integral de la velocidad da el tiempo de fuente).
            velocidad = elemento.animacion.valor("velocidad", elemento.local(f), elemento.tiempo.velocidad)
            filas.append(self._fila_animable(elemento, "velocidad", "velocidad", velocidad, "×", lambda v: v, None,
                                             aplicar_base=lambda v: self._velocidad(elemento, v)))
        if elemento.es_visual:
            filas.append(ft.Text("ESPACIO", size=TEMA.tamano_pequeno, color=TEMA.texto_suave))
            transform = elemento.transform_en(f)
            for propiedad, (etiqueta, a_pantalla, desde, unidad) in ESPACIO.items():
                filas.append(self._fila_animable(elemento, propiedad, etiqueta, a_pantalla(getattr(transform, propiedad)),
                                                 unidad, desde, base_ruta=f"espacio.{propiedad}"))
            filas.append(ft.Dropdown(
                dense=True, label="Mezcla", value=elemento.espacio.mezcla, width=180,
                options=[ft.DropdownOption(key=m, text=m) for m in MODOS_MEZCLA],
                on_select=lambda e: self._propiedad(elemento, "espacio.mezcla", e.control.value),
            ))
        if elemento.es_texto and elemento.texto is not None:
            filas += self._texto(elemento)
        if elemento.suena:
            filas.append(ft.Text("AUDIO", size=TEMA.tamano_pequeno, color=TEMA.texto_suave))
            for propiedad, (etiqueta, a_pantalla, desde, unidad) in AUDIO.items():
                valor = elemento.animacion.valor(propiedad, elemento.local(f), getattr(elemento.audio, propiedad))
                filas.append(self._fila_animable(elemento, propiedad, etiqueta, a_pantalla(valor), unidad, desde,
                                                 base_ruta=f"audio.{propiedad}"))
            filas.append(ft.Checkbox(label="Silenciado", value=elemento.audio.silenciado,
                                     on_change=lambda e: self._propiedad(elemento, "audio.silenciado", bool(e.control.value))))
            filas.append(self._campo_numero("fundido entrada", elemento.audio.fundido_entrada, "f",
                                            lambda v: self._propiedad(elemento, "audio.fundido_entrada", max(0, int(v)))))
            filas.append(self._campo_numero("fundido salida", elemento.audio.fundido_salida, "f",
                                            lambda v: self._propiedad(elemento, "audio.fundido_salida", max(0, int(v)))))
        filas += self._presets(elemento)
        filas += self._transicion(elemento)
        if elemento.es_visual:
            filas += self._efectos(elemento)
        self.cuerpo.controls = filas
        curvas = self.curvas
        if (curvas.indice_efecto is not None and curvas.propiedad and curvas.indice_efecto < len(elemento.efectos)
                and elemento.efectos[curvas.indice_efecto].animacion.tiene(curvas.propiedad)):
            curvas.mostrar(curvas.propiedad, curvas.indice_efecto)   # se sigue viendo el parámetro del efecto
        else:
            curvas.mostrar(self.propiedad_activa if elemento.animacion.tiene(self.propiedad_activa) else None)

    def _texto(self, elemento) -> list[ft.Control]:
        contenido = elemento.texto
        estilo = contenido.estilo
        return [
            ft.Text("TEXTO", size=TEMA.tamano_pequeno, color=TEMA.texto_suave),
            self._campo_texto("texto", contenido.texto, lambda v: self._propiedad(elemento, "texto.texto", v), multilinea=True),
            self._campo_numero("tamaño", estilo.tamano, "px",
                               lambda v: self._propiedad(elemento, "texto.estilo.tamano", max(1.0, v))),
            self._campo_texto("color", estilo.color, lambda v: self._propiedad(elemento, "texto.estilo.color", v.strip())),
            self._campo_numero("contorno", estilo.contorno_ancho, "px",
                               lambda v: self._propiedad(elemento, "texto.estilo.contorno_ancho", max(0.0, v))),
            ft.Dropdown(dense=True, label="Alineación", value=estilo.alineacion, width=180,
                        options=[ft.DropdownOption(key=a, text=a) for a in ALINEACIONES],
                        on_select=lambda e: self._propiedad(elemento, "texto.estilo.alineacion", e.control.value)),
            ft.Row([
                ft.Dropdown(dense=True, label="Entrada", value=contenido.animacion_entrada, width=150,
                            options=[ft.DropdownOption(key=a, text=ETIQUETAS_ANIMACION.get(a, a)) for a in ANIMACIONES_TEXTO],
                            on_select=lambda e: self._propiedad(elemento, "texto.animacion_entrada", e.control.value)),
                ft.Dropdown(dense=True, label="Salida", value=contenido.animacion_salida, width=150,
                            options=[ft.DropdownOption(key=a, text=ETIQUETAS_ANIMACION.get(a, a)) for a in ANIMACIONES_TEXTO],
                            on_select=lambda e: self._propiedad(elemento, "texto.animacion_salida", e.control.value)),
            ], wrap=True),
        ]

    def _historial(self) -> None:
        hechos, por_rehacer = self.sesion.historial.descripciones()
        filas: list[ft.Control] = [texto_suave(f"· {d}") for d in hechos[-12:]]
        filas += [ft.Text(f"↷ {d}", size=TEMA.tamano_pequeno, color=TEMA.borde) for d in por_rehacer[:6]]
        self.historial.controls = filas or [texto_suave("Sin cambios.")]

    # --- Campos ------------------------------------------------------------------------

    def _campo_texto(self, etiqueta: str, valor: str, aplicar: Callable[[str], None], multilinea: bool = False) -> ft.TextField:
        def enviar(evento) -> None:
            nuevo = evento.control.value or ""
            if nuevo != valor:
                aplicar(nuevo)

        return ft.TextField(
            label=etiqueta, value=valor, dense=True, text_size=TEMA.tamano_texto, multiline=multilinea,
            min_lines=2 if multilinea else None, max_lines=4 if multilinea else 1,
            on_submit=enviar, on_blur=lambda e: (enviar(e), self.app.enfocar("timeline")),
            on_focus=lambda _: self.app.enfocar("texto"),
        )

    def _campo_numero(self, etiqueta: str, valor: float, unidad: str, aplicar: Callable[[float], None],
                      ancho: int = 110) -> ft.TextField:
        def enviar(evento) -> None:
            try:
                nuevo = float((evento.control.value or "").replace(",", "."))
            except ValueError:
                self.app.aviso_breve(f"{etiqueta}: número inválido")
                return
            if abs(nuevo - valor) > 1e-9:
                aplicar(nuevo)

        return ft.TextField(
            label=etiqueta, value=_numero(valor), suffix=unidad, dense=True, width=ancho,
            text_size=TEMA.tamano_texto, keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=enviar, on_blur=lambda e: (enviar(e), self.app.enfocar("timeline")),
            on_focus=lambda _: self.app.enfocar("texto"),
        )

    def _fila_animable(self, elemento, propiedad: str, etiqueta: str, valor_pantalla: float, unidad: str,
                       desde_pantalla: Callable[[float], float], base_ruta: str | None,
                       indice_efecto: int | None = None,
                       aplicar_base: Callable[[float], None] | None = None) -> ft.Control:
        """Campo con rombo de keyframe. `indice_efecto`: parámetro del efecto en esa posición."""
        f_local = self.sesion.estado.cabezal - elemento.inicio
        animacion = _animacion(elemento, indice_efecto)
        animada = animacion.tiene(propiedad)
        en_cabezal = animada and animacion.pista(propiedad).obtener(f_local) is not None

        def aplicar(nuevo: float) -> None:
            self.propiedad_activa = propiedad
            valor = desde_pantalla(nuevo)
            if animada:
                self._poner_keyframe(elemento, propiedad, valor, indice_efecto)
            elif aplicar_base is not None:
                aplicar_base(valor)
            elif indice_efecto is not None:
                self._ejecutar(lambda: CambiarParametroEfecto(self.sesion.estado.capitulo, elemento.id,
                                                              indice_efecto, propiedad, valor))
            else:
                self._propiedad(elemento, base_ruta, valor)

        rombo = ft.IconButton(
            ft.Icons.DIAMOND if en_cabezal else ft.Icons.DIAMOND_OUTLINED,
            icon_color=TEMA.marcador if animada else TEMA.texto_suave, icon_size=16, width=30, height=30,
            tooltip="Quitar keyframe" if en_cabezal else "Poner keyframe en el cabezal",
            on_click=lambda _: self._alternar_keyframe(elemento, propiedad, desde_pantalla(valor_pantalla),
                                                       en_cabezal, indice_efecto),
        )
        navegar = [
            ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_size=14, width=24, height=24, disabled=not animada,
                          tooltip="Keyframe anterior",
                          on_click=lambda _: self._saltar(elemento, propiedad, -1, indice_efecto)),
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_size=14, width=24, height=24, disabled=not animada,
                          tooltip="Keyframe siguiente",
                          on_click=lambda _: self._saltar(elemento, propiedad, 1, indice_efecto)),
        ]
        campo = self._campo_numero(etiqueta, valor_pantalla, unidad, aplicar)
        fila = ft.Row([rombo, campo, *navegar], spacing=0)
        return ft.GestureDetector(content=fila, on_tap=lambda _: self._activar(propiedad, indice_efecto))

    def _presets(self, elemento) -> list[ft.Control]:
        """Atajos de animación y de audio; cada uno es un paso de deshacer."""
        botones: list[ft.Control] = []
        sesion = self.sesion
        refrescar = lambda hecho: hecho and self.app.refrescar("inspector", "monitor", "timeline")  # noqa: E731
        if elemento.es_visual and not elemento.es_texto:
            botones.append(ft.OutlinedButton("Ken Burns", icon=ft.Icons.ZOOM_IN_MAP,
                                             on_click=lambda _: refrescar(ctl_creativo.ken_burns(sesion, elemento.id))))
            botones.append(ft.OutlinedButton("Estabilizar", icon=ft.Icons.CENTER_FOCUS_STRONG,
                                             on_click=lambda _: ctl_creativo.estabilizar(sesion, elemento.id)))
        if elemento.es_visual:
            tipo = ft.Dropdown(dense=True, width=130, value="fundido",
                               options=[ft.DropdownOption(key=t, text=t) for t in ANIMACIONES_CLIP])
            botones.append(ft.Row([
                tipo,
                ft.TextButton("Entrada", on_click=lambda _: refrescar(
                    ctl_creativo.animar_clip(sesion, elemento.id, tipo.value or "fundido", True))),
                ft.TextButton("Salida", on_click=lambda _: refrescar(
                    ctl_creativo.animar_clip(sesion, elemento.id, tipo.value or "fundido", False))),
            ], spacing=0))
        if elemento.suena and elemento.capa.tipo.value == "A":
            botones.append(ft.OutlinedButton(
                "Bajar con la voz", icon=ft.Icons.GRAPHIC_EQ,
                tooltip="Ducking: baja esta música 12 dB mientras suenan las voces (capas con idioma)",
                on_click=lambda _: ctl_audio.ducking(sesion, elemento.id)))
        if not botones:
            return []
        return [ft.Text("PRESETS", size=TEMA.tamano_pequeno, color=TEMA.texto_suave), ft.Row(botones, wrap=True)]

    def _transicion(self, elemento) -> list[ft.Control]:
        """Transición de entrada: solapa con el Elemento anterior de la capa durante su duración."""
        actual = elemento.transicion_entrada
        ninguna = "ninguna"

        def cambiar(tipo=None, duracion=None, direccion=None) -> None:
            elegido = tipo if tipo is not None else (actual.tipo if actual else None)
            if elegido in (None, ninguna):
                hecho = ctl_timeline.cambiar_transicion(self.sesion, elemento.id, None)
            else:
                hecho = ctl_timeline.cambiar_transicion(self.sesion, elemento.id, elegido, duracion, direccion)
            if hecho:
                self.app.refrescar("inspector", "timeline", "monitor", "mapa")

        filas: list[ft.Control] = [ft.Text("TRANSICIÓN DE ENTRADA", size=TEMA.tamano_pequeno, color=TEMA.texto_suave),
                                   ft.Dropdown(
                                       dense=True, width=200, label="Tipo", value=actual.tipo if actual else ninguna,
                                       options=[ft.DropdownOption(key=ninguna, text="Ninguna")] + [
                                           ft.DropdownOption(key=t, text=descriptor_transicion(t).etiqueta)
                                           for t in tipos_transicion()],
                                       on_select=lambda e: cambiar(tipo=e.control.value))]
        if actual is not None:
            filas.append(self._campo_numero("duración", actual.duracion, "f",
                                            lambda v: cambiar(duracion=max(1, int(v)))))
            if descriptor_transicion(actual.tipo).usa_direccion:
                filas.append(ft.Dropdown(
                    dense=True, width=200, label="Dirección", value=actual.direccion,
                    options=[ft.DropdownOption(key=d, text=d) for d in DIRECCIONES],
                    on_select=lambda e: cambiar(direccion=e.control.value)))
        return filas

    def _efectos(self, elemento) -> list[ft.Control]:
        """Pila de efectos: agregar, activar, parámetros con keyframes, opciones, subir y quitar."""
        capitulo = self.sesion.estado.capitulo
        filas: list[ft.Control] = [ft.Row([
            ft.Text("EFECTOS", size=TEMA.tamano_pequeno, color=TEMA.texto_suave),
            ft.Dropdown(dense=True, width=190, label="Agregar efecto", value=None,
                        options=[ft.DropdownOption(key=t, text=descriptor_efecto(t).etiqueta) for t in tipos_efecto()],
                        on_select=lambda e: e.control.value and self._ejecutar(
                            lambda: AgregarEfecto(capitulo, elemento.id, efecto_nuevo(e.control.value)))),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)]
        f_local = elemento.local(self.sesion.estado.cabezal)
        for indice, efecto in enumerate(elemento.efectos):
            descriptor = descriptor_efecto(efecto.tipo)
            filas.append(ft.Row([
                ft.Checkbox(label=descriptor.etiqueta, value=efecto.activo,
                            on_change=lambda e, i=indice: self._ejecutar(
                                lambda: ActivarEfecto(capitulo, elemento.id, i, bool(e.control.value)))),
                ft.Row([
                    ft.IconButton(ft.Icons.ARROW_UPWARD, icon_size=14, width=26, height=26, tooltip="Subir",
                                  disabled=indice == 0,
                                  on_click=lambda _, i=indice: self._ejecutar(
                                      lambda: ReordenarEfecto(capitulo, elemento.id, i, i - 1))),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=14, width=26, height=26, tooltip="Quitar",
                                  on_click=lambda _, i=indice: self._ejecutar(
                                      lambda: QuitarEfecto(capitulo, elemento.id, i))),
                ], spacing=0),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
            for parametro in descriptor.parametros:
                valor = efecto.valor(parametro.nombre, f_local)
                filas.append(self._fila_animable(
                    elemento, parametro.nombre, parametro.nombre, valor, parametro.unidad,
                    lambda v, p=parametro: max(p.minimo, min(p.maximo, v)), None, indice_efecto=indice))
            for opcion, _defecto in descriptor.opciones:
                filas.append(self._campo_texto(
                    opcion, efecto.opciones.get(opcion, ""),
                    lambda v, i=indice, o=opcion: self._ejecutar(
                        lambda: CambiarOpcionEfecto(capitulo, elemento.id, i, o, v.strip()))))
        return filas

    # --- Acciones ----------------------------------------------------------------------

    def _ejecutar(self, construir) -> None:
        if self.sesion.ejecutar(construir):
            self.app.refrescar("inspector", "monitor", "timeline", "mapa")

    def _propiedad(self, elemento, ruta: str, valor) -> None:
        self._ejecutar(lambda: CambiarPropiedad(self.sesion.estado.capitulo, elemento.id, ruta, valor))

    def _velocidad(self, elemento, valor: float) -> None:
        self._ejecutar(lambda: CambiarVelocidad(self.sesion.estado.capitulo, elemento.id, valor))

    def _poner_keyframe(self, elemento, propiedad: str, valor: float, indice_efecto: int | None = None) -> None:
        f_local = self.sesion.estado.cabezal - elemento.inicio
        if not 0 <= f_local < elemento.duracion:
            self.app.avisar("El cabezal no está sobre el Elemento.")
            return
        animacion = _animacion(elemento, indice_efecto)
        previo = animacion.pista(propiedad).obtener(f_local) if animacion.tiene(propiedad) else None
        keyframe = Keyframe(f_local, float(valor), previo.curva if previo else "lineal", previo.controles if previo else None)
        self._ejecutar(lambda: PonerKeyframe(self.sesion.estado.capitulo, elemento.id, propiedad, keyframe, indice_efecto))

    def _alternar_keyframe(self, elemento, propiedad: str, valor: float, hay: bool,
                           indice_efecto: int | None = None) -> None:
        if indice_efecto is None:
            self.propiedad_activa = propiedad
        if hay:
            f_local = self.sesion.estado.cabezal - elemento.inicio
            self._ejecutar(lambda: QuitarKeyframe(self.sesion.estado.capitulo, elemento.id, propiedad, f_local,
                                                  indice_efecto))
        else:
            self._poner_keyframe(elemento, propiedad, valor, indice_efecto)

    def agregar_keyframe(self) -> None:
        """Atajo K: keyframe de la propiedad activa (por defecto, la posición x e y)."""
        elemento = self.sesion.seleccionado()
        if elemento is None:
            return
        f = self.sesion.estado.cabezal
        propiedades = [self.propiedad_activa] if self.propiedad_activa not in ("x", "y") else ["x", "y"]
        for propiedad in propiedades:
            if propiedad in ESPACIO and elemento.es_visual:
                self._poner_keyframe(elemento, propiedad, getattr(elemento.transform_en(f), propiedad))
            elif propiedad in AUDIO and elemento.suena:
                valor = elemento.animacion.valor(propiedad, elemento.local(f), getattr(elemento.audio, propiedad))
                self._poner_keyframe(elemento, propiedad, valor)

    def _saltar(self, elemento, propiedad: str, direccion: int, indice_efecto: int | None = None) -> None:
        animacion = _animacion(elemento, indice_efecto)
        if not animacion.tiene(propiedad):
            return
        f_local = self.sesion.estado.cabezal - elemento.inicio
        posiciones = [k.f for k in animacion.pista(propiedad)]
        destino = ([f for f in posiciones if f > f_local][:1] if direccion > 0
                   else [f for f in posiciones if f < f_local][-1:])
        if destino:
            if indice_efecto is None:
                self.propiedad_activa = propiedad
            self.app.mover_cabezal_a(elemento.inicio + destino[0])

    def _activar(self, propiedad: str, indice_efecto: int | None = None) -> None:
        """La propiedad (o el parámetro de efecto) que muestra el editor de curvas."""
        if indice_efecto is None:
            self.propiedad_activa = propiedad
        elemento = self.sesion.seleccionado()
        animada = elemento is not None and _animacion(elemento, indice_efecto).tiene(propiedad)
        self.curvas.mostrar(propiedad if animada else None, indice_efecto)
        actualizar(self.curvas.control)


def _animacion(elemento, indice_efecto: int | None):
    return elemento.animacion if indice_efecto is None else elemento.efectos[indice_efecto].animacion


def _numero(valor: float) -> str:
    return f"{valor:.2f}".rstrip("0").rstrip(".") if isinstance(valor, float) else str(valor)
