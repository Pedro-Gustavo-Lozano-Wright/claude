"""Propiedades del Elemento seleccionado, keyframes e historial (E16).

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
from editor.core.comandos import ActivarEfecto, CambiarPropiedad, CambiarVelocidad, PonerKeyframe, QuitarKeyframe
from editor.core.espacio.transform import MODOS_MEZCLA
from editor.core.modelo.keyframe import Keyframe
from editor.core.modelo.texto import ALINEACIONES, ANIMACIONES_TEXTO
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
            ], wrap=True),
        ]
        if not elemento.es_texto:
            filas.append(self._campo_numero("velocidad", elemento.tiempo.velocidad, "×",
                                            lambda v: self._velocidad(elemento, v)))
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
        if elemento.efectos:
            filas.append(ft.Text("EFECTOS", size=TEMA.tamano_pequeno, color=TEMA.texto_suave))
            for indice, efecto in enumerate(elemento.efectos):
                filas.append(ft.Checkbox(
                    label=efecto.tipo, value=efecto.activo,
                    on_change=lambda e, i=indice: self._ejecutar(
                        lambda: ActivarEfecto(self.sesion.estado.capitulo, elemento.id, i, bool(e.control.value))),
                ))
        self.cuerpo.controls = filas
        self.curvas.mostrar(self.propiedad_activa if elemento.animacion.tiene(self.propiedad_activa) else None)

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
                            options=[ft.DropdownOption(key=a, text=a) for a in ANIMACIONES_TEXTO],
                            on_select=lambda e: self._propiedad(elemento, "texto.animacion_entrada", e.control.value)),
                ft.Dropdown(dense=True, label="Salida", value=contenido.animacion_salida, width=150,
                            options=[ft.DropdownOption(key=a, text=a) for a in ANIMACIONES_TEXTO],
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
                       desde_pantalla: Callable[[float], float], base_ruta: str) -> ft.Control:
        f_local = self.sesion.estado.cabezal - elemento.inicio
        animada = elemento.animacion.tiene(propiedad)
        en_cabezal = animada and elemento.animacion.pista(propiedad).obtener(f_local) is not None

        def aplicar(nuevo: float) -> None:
            self.propiedad_activa = propiedad
            valor = desde_pantalla(nuevo)
            if animada:
                self._poner_keyframe(elemento, propiedad, valor)
            else:
                self._propiedad(elemento, base_ruta, valor)

        rombo = ft.IconButton(
            ft.Icons.DIAMOND if en_cabezal else ft.Icons.DIAMOND_OUTLINED,
            icon_color=TEMA.marcador if animada else TEMA.texto_suave, icon_size=16, width=30, height=30,
            tooltip="Quitar keyframe" if en_cabezal else "Poner keyframe en el cabezal",
            on_click=lambda _: self._alternar_keyframe(elemento, propiedad, desde_pantalla(valor_pantalla), en_cabezal),
        )
        navegar = [
            ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_size=14, width=24, height=24, disabled=not animada,
                          tooltip="Keyframe anterior", on_click=lambda _: self._saltar(elemento, propiedad, -1)),
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_size=14, width=24, height=24, disabled=not animada,
                          tooltip="Keyframe siguiente", on_click=lambda _: self._saltar(elemento, propiedad, 1)),
        ]
        campo = self._campo_numero(etiqueta, valor_pantalla, unidad, aplicar)
        return ft.GestureDetector(
            content=ft.Row([rombo, campo, *navegar], spacing=0),
            on_tap=lambda _: self._activar(propiedad),
        )

    # --- Acciones ----------------------------------------------------------------------

    def _ejecutar(self, construir) -> None:
        if self.sesion.ejecutar(construir):
            self.app.refrescar("inspector", "monitor", "timeline", "mapa")

    def _propiedad(self, elemento, ruta: str, valor) -> None:
        self._ejecutar(lambda: CambiarPropiedad(self.sesion.estado.capitulo, elemento.id, ruta, valor))

    def _velocidad(self, elemento, valor: float) -> None:
        self._ejecutar(lambda: CambiarVelocidad(self.sesion.estado.capitulo, elemento.id, valor))

    def _poner_keyframe(self, elemento, propiedad: str, valor: float) -> None:
        f_local = self.sesion.estado.cabezal - elemento.inicio
        if not 0 <= f_local < elemento.duracion:
            self.app.avisar("El cabezal no está sobre el Elemento.")
            return
        previo = elemento.animacion.pista(propiedad).obtener(f_local) if elemento.animacion.tiene(propiedad) else None
        keyframe = Keyframe(f_local, float(valor), previo.curva if previo else "lineal", previo.controles if previo else None)
        self._ejecutar(lambda: PonerKeyframe(self.sesion.estado.capitulo, elemento.id, propiedad, keyframe))

    def _alternar_keyframe(self, elemento, propiedad: str, valor: float, hay: bool) -> None:
        self.propiedad_activa = propiedad
        if hay:
            f_local = self.sesion.estado.cabezal - elemento.inicio
            self._ejecutar(lambda: QuitarKeyframe(self.sesion.estado.capitulo, elemento.id, propiedad, f_local))
        else:
            self._poner_keyframe(elemento, propiedad, valor)

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

    def _saltar(self, elemento, propiedad: str, direccion: int) -> None:
        if not elemento.animacion.tiene(propiedad):
            return
        f_local = self.sesion.estado.cabezal - elemento.inicio
        posiciones = [k.f for k in elemento.animacion.pista(propiedad)]
        destino = ([f for f in posiciones if f > f_local][:1] if direccion > 0
                   else [f for f in posiciones if f < f_local][-1:])
        if destino:
            self.propiedad_activa = propiedad
            self.app.mover_cabezal_a(elemento.inicio + destino[0])

    def _activar(self, propiedad: str) -> None:
        self.propiedad_activa = propiedad
        elemento = self.sesion.seleccionado()
        self.curvas.mostrar(propiedad if elemento is not None and elemento.animacion.tiene(propiedad) else None)
        actualizar(self.curvas.control)


def _numero(valor: float) -> str:
    return f"{valor:.2f}".rstrip("0").rstrip(".") if isinstance(valor, float) else str(valor)
