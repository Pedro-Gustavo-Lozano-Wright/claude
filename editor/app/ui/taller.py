"""Vista del Taller: Brutos → Piezas → horneado (E15, PROJECT.md 16.5).

Con un Bruto elegido: visor en fotogramas **nativos**, marcas de entrada y
salida (I / O con el foco en el Taller), fps interpretado y método de
conversión → "Crear Pieza" o "Añadir tramo". Con una Pieza elegida: sus
tramos, método, estado del horneado, hornear y colocar.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

import flet as ft

from editor.app.controladores import audio as ctl_audio
from editor.app.controladores import taller as ctl
from editor.app.ui.tema import TEMA, texto, texto_suave, titulo_panel
from editor.app.ui.widgets import actualizar, timecode
from editor.app.ui.widgets.imagen import imagen_vacia
from editor.core.comandos.taller import QuitarPieza
from editor.core.estandar import FPS
from editor.core.modelo.bruto import TipoMedio
from editor.core.modelo.pieza import AudioConformado, MetodoConversionFps
from editor.core.tiempo.granularidad import FPS_COMUNES, texto_fps

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana

NOMBRES_METODO = {
    MetodoConversionFps.TIEMPO: "Tiempo real (descarta o duplica)",
    MetodoConversionFps.CONFORMAR: "Conformar (fotograma a fotograma)",
    MetodoConversionFps.CAMARA_LENTA: "Cámara lenta",
    MetodoConversionFps.MEZCLA: "Mezcla de fotogramas",
    MetodoConversionFps.INTERPOLACION: "Interpolación (flujo óptico)",
}
NOMBRES_AUDIO = {
    AudioConformado.CONSERVAR_TONO: "Estirar conservando el tono",
    AudioConformado.ESTIRAR_CON_TONO: "Estirar (cambia el tono)",
    AudioConformado.SILENCIAR: "Silenciar",
}
AUTOMATICO = "auto"
ALTO_VISOR = 300


class Taller:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self.id_bruto: str | None = None
        self.escenas: dict[str, list[int]] = {}      # resultados del análisis por Bruto
        self.silencios: dict[str, list] = {}
        self.id_pieza: str | None = None
        self.posicion = 0
        self.entrada: int | None = None
        self.salida: int | None = None
        self._arrastrando = False

        self.visor = ft.Image(src=imagen_vacia(), gapless_playback=True, fit=ft.BoxFit.CONTAIN)
        self.deslizador = ft.Slider(min=0, max=1, value=0, expand=True,
                                    on_change=self._deslizar, on_change_end=self._soltar_deslizador)
        self.posicion_texto = texto_suave("")
        self.marcas_texto = texto_suave("")
        self.fps = ft.Dropdown(dense=True, width=170, label="fps interpretado", on_select=self._interpretar)
        self.metodo = ft.Dropdown(
            dense=True, width=260, label="Conversión a 24 fps", value=MetodoConversionFps.TIEMPO.value,
            options=[ft.DropdownOption(key=m.value, text=t) for m, t in NOMBRES_METODO.items()],
            on_select=self._cambiar_metodo,
        )
        self.nombre = ft.TextField(dense=True, label="Nombre de la Pieza", width=260, text_size=TEMA.tamano_texto,
                                   on_focus=lambda _: app.enfocar("texto"), on_blur=lambda _: app.enfocar("taller"))
        self.info = ft.Column(spacing=2)
        self.acciones = ft.Row(spacing=6, wrap=True)
        self.control = ft.Container(
            content=ft.Column(
                [
                    titulo_panel("Taller"),
                    # Alto fijo: dentro de una columna con scroll, `expand` no reparte altura.
                    ft.Container(self.visor, bgcolor=TEMA.lienzo, height=ALTO_VISOR, alignment=ft.Alignment.CENTER),
                    ft.Row([self.deslizador, self.posicion_texto]),
                    self.marcas_texto,
                    ft.Row([self.fps, self.metodo, self.nombre], wrap=True),
                    self.info,
                    self.acciones,
                ],
                spacing=6,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            bgcolor=TEMA.panel,
            padding=6,
            expand=True,
            on_click=lambda _: app.enfocar("taller"),
        )

    @property
    def sesion(self):
        return self.app.sesion

    # --- Selección ---------------------------------------------------------------------

    def abrir_bruto(self, id_bruto: str) -> None:
        if id_bruto != self.id_bruto:
            self.id_bruto = id_bruto
            self.posicion = 0
            self.entrada = self.salida = None
            bruto = self.sesion.proyecto.taller.bruto(id_bruto)
            self.nombre.value = bruto.nombre
        self._pedir_visor()

    def abrir_pieza(self, id_pieza: str) -> None:
        self.id_pieza = id_pieza
        pieza = self.sesion.proyecto.taller.pieza(id_pieza)
        self.metodo.value = pieza.metodo_fps.value
        self.nombre.value = pieza.nombre
        if pieza.tramos:
            tramo = pieza.tramos[0]
            self.id_bruto = tramo.id_bruto
            self.entrada, self.salida = tramo.entrada, tramo.salida
            self.posicion = tramo.entrada
            self._pedir_visor()

    # --- Dibujo ------------------------------------------------------------------------

    def refrescar(self) -> None:
        taller = self.sesion.proyecto.taller
        if self.id_bruto is not None and self.id_bruto not in taller.brutos:
            self.id_bruto = None
        if self.id_pieza is not None and self.id_pieza not in taller.piezas:
            self.id_pieza = None
        bruto = taller.brutos.get(self.id_bruto) if self.id_bruto else None
        pieza = taller.piezas.get(self.id_pieza) if self.id_pieza else None
        info: list[ft.Control] = []
        acciones: list[ft.Control] = []

        if bruto is None:
            info.append(texto_suave("Elija un Bruto en el navegador para preparar una Pieza."))
            self.deslizador.disabled = True
        else:
            total = max(1, bruto.fotogramas_nativos)
            self.deslizador.disabled = False
            self.deslizador.max = max(1, total - 1)
            self.deslizador.divisions = min(total - 1, 2000) or None
            self.deslizador.value = min(self.posicion, total - 1)
            fps = bruto.fps
            segundos = f" · {float(Fraction(self.posicion) / fps):.2f} s" if fps else ""
            self.posicion_texto.value = f"f {self.posicion} / {total - 1}{segundos}"
            self.fps.options = [ft.DropdownOption(key=AUTOMATICO, text="Automático")] + [
                ft.DropdownOption(key=t, text=f"{t} fps") for t in FPS_COMUNES
            ]
            self.fps.value = texto_fps(bruto.fps_interpretado) if bruto.fps_interpretado else AUTOMATICO
            self.fps.disabled = bruto.tipo is not TipoMedio.VIDEO
            info.append(texto(f"{bruto.numero:03d} {bruto.nombre}", weight=ft.FontWeight.BOLD))
            detalles = [bruto.tipo.value]
            if bruto.ancho:
                detalles.append(f"{bruto.ancho}×{bruto.alto}")
            if bruto.fps_detectado:
                detalles.append(f"declarado {texto_fps(bruto.fps_detectado)}")
            if bruto.fps_medido:
                detalles.append(f"medido {texto_fps(bruto.fps_medido)}")
            if bruto.vfr:
                detalles.append("fps variable")
            if bruto.tiene_alfa:
                detalles.append("alfa")
            if bruto.tiene_audio:
                detalles.append("audio")
            info.append(texto_suave(" · ".join(detalles)))
            if bruto.necesita_revision_fps:
                info.append(ft.Text("El fps declarado no coincide con el medido (o es variable): elija el correcto.",
                                    color=TEMA.error, size=TEMA.tamano_pequeno))
            acciones += [
                ft.OutlinedButton("Entrada (I)", on_click=lambda _: self.marcar_entrada()),
                ft.OutlinedButton("Salida (O)", on_click=lambda _: self.marcar_salida()),
                ft.FilledButton("Crear Pieza", icon=ft.Icons.ADD, on_click=lambda _: self._crear_pieza()),
                ft.TextButton("Quitar Bruto", icon=ft.Icons.DELETE, on_click=lambda _: self._quitar_bruto()),
            ]
            if pieza is not None:
                acciones.append(ft.OutlinedButton(f"Añadir tramo a P{pieza.numero:03d}",
                                                  on_click=lambda _: self._agregar_tramo()))
            info += self._analisis(bruto)
        self.marcas_texto.value = self._texto_marcas(bruto)

        if pieza is not None:
            info.append(ft.Divider())
            estado = ("sin hornear" if pieza.horneado is None else
                      f"horneada v{pieza.version}" if pieza.horneada_al_dia else "receta cambiada: hay que hornear")
            duracion = pieza.fotogramas_24(taller.brutos) if all(t.id_bruto in taller.brutos for t in pieza.tramos) else 0
            info.append(texto(f"Pieza P{pieza.numero:03d} {pieza.nombre} · {estado}", weight=ft.FontWeight.BOLD))
            info.append(texto_suave(f"{NOMBRES_METODO[pieza.metodo_fps]} · {timecode.duracion(duracion)} a {FPS} fps"))
            for i, tramo in enumerate(pieza.tramos, 1):
                origen = taller.brutos.get(tramo.id_bruto)
                info.append(texto_suave(f"  tramo {i}: {origen.nombre if origen else tramo.id_bruto} "
                                        f"[{tramo.entrada}, {tramo.salida}) · {tramo.fotogramas_nativos} f nativos"))
            if not pieza.metodo_fps.conserva_tiempo:
                # El método cambia la duración: qué hacer con el audio.
                info.append(ft.Dropdown(
                    dense=True, width=260, label="Audio al cambiar la duración", value=pieza.audio_conformado.value,
                    options=[ft.DropdownOption(key=m.value, text=t) for m, t in NOMBRES_AUDIO.items()],
                    on_select=lambda e, i=pieza.id: self._audio_conformado(i, e.control.value)))
            acciones += [
                ft.FilledButton("Hornear", icon=ft.Icons.LOCAL_FIRE_DEPARTMENT,
                                on_click=lambda _: self._hornear(), disabled=pieza.horneada_al_dia),
                ft.OutlinedButton("Colocar en el cabezal", icon=ft.Icons.PLAYLIST_ADD,
                                  disabled=pieza.horneado is None, on_click=lambda _: self._colocar()),
                ft.TextButton("Quitar Pieza", icon=ft.Icons.DELETE, on_click=lambda _: self._quitar_pieza()),
            ]
        self.info.controls = info
        self.acciones.controls = acciones

    # --- Análisis (E17): escenas, silencios y audio externo -------------------------------

    def _analisis(self, bruto) -> list[ft.Control]:
        filas: list[ft.Control] = [ft.Divider()]
        botones: list[ft.Control] = []
        if bruto.tipo is TipoMedio.VIDEO:
            botones.append(ft.OutlinedButton("Buscar escenas", icon=ft.Icons.MOVIE_FILTER,
                                             on_click=lambda _: self._buscar_escenas(bruto.id)))
        if bruto.tiene_audio or bruto.tipo is TipoMedio.AUDIO:
            botones.append(ft.OutlinedButton("Buscar silencios", icon=ft.Icons.VOLUME_OFF,
                                             on_click=lambda _: self._buscar_silencios(bruto.id)))
        if bruto.tiene_audio or bruto.tipo is TipoMedio.AUDIO:
            botones.append(ft.OutlinedButton(
                "Reducir ruido", icon=ft.Icons.NOISE_CONTROL_OFF,
                tooltip="Crea un Bruto nuevo con el ruido de fondo reducido (el original no cambia)",
                on_click=lambda _: self._reducir_ruido(bruto.id)))
        if bruto.tipo is TipoMedio.AUDIO:
            botones.append(ft.OutlinedButton(
                "Alinear con el Elemento seleccionado", icon=ft.Icons.SYNC,
                tooltip="Coloca este audio sincronizado con el sonido del Elemento elegido en la timeline",
                on_click=lambda _: self._alinear(bruto.id)))
        if botones:
            filas.append(ft.Row(botones, wrap=True, spacing=6))
        fps = bruto.fps or Fraction(FPS)
        escenas = self.escenas.get(bruto.id)
        if escenas is not None:
            filas.append(texto_suave(f"Escenas: {len(escenas)} cortes (clic: ir al corte y marcar entrada)"))
            filas.append(ft.Row([ft.TextButton(f"f {f}", on_click=lambda _, n=f: self._ir_y_marcar(n, entrada=True))
                                 for f in escenas[:40]], wrap=True, spacing=0))
        silencios = self.silencios.get(bruto.id)
        if silencios is not None:
            filas.append(texto_suave(f"Silencios: {len(silencios)} (clic: ir al final del silencio y marcar entrada)"))
            filas.append(ft.Row([
                ft.TextButton(f"{s.inicio:.1f}–{s.fin:.1f} s",
                              on_click=lambda _, n=int(s.fin * fps): self._ir_y_marcar(n, entrada=True))
                for s in silencios[:40]], wrap=True, spacing=0))
        return filas

    def _reducir_ruido(self, id_bruto: str) -> None:
        ctl_audio.reducir_ruido(self.sesion, id_bruto)
        self.app.aviso_breve("Reduciendo ruido…")

    def _audio_conformado(self, id_pieza: str, valor: str | None) -> None:
        if valor and ctl.cambiar_audio_conformado(self.sesion, id_pieza, AudioConformado(valor)):
            self.app.refrescar("taller", "navegador")

    def _buscar_escenas(self, id_bruto: str) -> None:
        def listo(cortes) -> None:
            self.escenas[id_bruto] = cortes
            self.app.refrescar("taller")
        ctl.detectar_escenas(self.sesion, id_bruto, listo)
        self.app.aviso_breve("Buscando escenas…")

    def _buscar_silencios(self, id_bruto: str) -> None:
        def listo(tramos) -> None:
            self.silencios[id_bruto] = tramos
            self.app.refrescar("taller")
        ctl.detectar_silencios(self.sesion, id_bruto, listo)
        self.app.aviso_breve("Buscando silencios…")

    def _alinear(self, id_bruto: str) -> None:
        referencia = self.sesion.seleccionado()
        if referencia is None:
            self.app.avisar("Elija primero en la timeline el Elemento con el sonido de referencia.")
            return
        ctl.sincronizar_audio(self.sesion, referencia.id, id_bruto)
        self.app.aviso_breve("Comparando audio…")

    def _ir_y_marcar(self, fotograma: int, entrada: bool) -> None:
        self.posicion = max(0, fotograma)
        self.marcar_entrada() if entrada else self.marcar_salida()
        self._pedir_visor()

    def _texto_marcas(self, bruto) -> str:
        if bruto is None:
            return ""
        partes = [f"entrada {self.entrada if self.entrada is not None else '—'}",
                  f"salida {self.salida if self.salida is not None else '—'}"]
        if self.entrada is not None and self.salida is not None and self.salida > self.entrada and bruto.fps:
            nativos = self.salida - self.entrada
            metodo = MetodoConversionFps(self.metodo.value or MetodoConversionFps.TIEMPO.value)
            from editor.core.tiempo.granularidad import fotogramas_24_de_tramo

            a24 = fotogramas_24_de_tramo(nativos, bruto.fps, metodo.conserva_tiempo)
            partes.append(f"{nativos} f nativos → {a24} f a 24 fps ({timecode.duracion(a24)})")
        return " · ".join(partes)

    # --- Visor -------------------------------------------------------------------------

    def _pedir_visor(self) -> None:
        if self.id_bruto is None:
            return

        def llegar(datos: bytes, n: int) -> None:
            if n == self.posicion:
                self.visor.src = datos
                actualizar(self.visor)

        ctl.fotograma_bruto(self.sesion, self.id_bruto, self.posicion, llegar)

    def _deslizar(self, evento) -> None:
        self.posicion = int(evento.control.value or 0)
        self.posicion_texto.value = f"f {self.posicion}"
        self._pedir_visor()

    def _soltar_deslizador(self, _evento) -> None:
        self.app.enfocar("taller")
        self.refrescar()

    def mover(self, delta: int) -> None:
        if self.id_bruto is None:
            return
        total = self.sesion.proyecto.taller.bruto(self.id_bruto).fotogramas_nativos
        self.posicion = max(0, min(max(0, total - 1), self.posicion + delta))
        self._pedir_visor()
        self.refrescar()

    def marcar_entrada(self) -> None:
        self.entrada = self.posicion
        if self.salida is not None and self.salida <= self.entrada:
            self.salida = None
        self.refrescar()

    def marcar_salida(self) -> None:
        self.salida = self.posicion + 1          # la salida es excluyente: incluye el fotograma visto
        if self.entrada is not None and self.salida <= self.entrada:
            self.entrada = None
        self.refrescar()

    # --- Acciones ----------------------------------------------------------------------

    def _rango(self) -> tuple[int, int] | None:
        bruto = self.sesion.proyecto.taller.bruto(self.id_bruto) if self.id_bruto else None
        if bruto is None:
            return None
        entrada = self.entrada if self.entrada is not None else 0
        salida = self.salida if self.salida is not None else max(1, bruto.fotogramas_nativos)
        if salida <= entrada:
            self.app.avisar("La salida debe ir después de la entrada.")
            return None
        return entrada, salida

    def _crear_pieza(self) -> None:
        rango = self._rango()
        if rango is None:
            return
        metodo = MetodoConversionFps(self.metodo.value or MetodoConversionFps.TIEMPO.value)
        id_pieza = ctl.crear_pieza(self.sesion, self.id_bruto, *rango, metodo=metodo, nombre=self.nombre.value or None)
        if id_pieza is not None:
            self.id_pieza = id_pieza
            self.app.refrescar("taller", "navegador")

    def _agregar_tramo(self) -> None:
        rango = self._rango()
        if rango is not None and self.id_pieza and ctl.agregar_tramo(self.sesion, self.id_pieza, self.id_bruto, *rango):
            self.app.refrescar("taller", "navegador")

    def _interpretar(self, evento) -> None:
        if self.id_bruto is None:
            return
        valor = evento.control.value
        fps = None if valor in (None, AUTOMATICO) else FPS_COMUNES[valor]
        if ctl.interpretar_fps(self.sesion, self.id_bruto, fps):
            self.app.refrescar("taller", "navegador")

    def _cambiar_metodo(self, evento) -> None:
        metodo = MetodoConversionFps(evento.control.value)
        if self.id_pieza and ctl.cambiar_metodo(self.sesion, self.id_pieza, metodo):
            self.app.refrescar("navegador")
        self.refrescar()

    def _hornear(self) -> None:
        if self.id_pieza:
            ctl.hornear(self.sesion, self.id_pieza)
            self.app.aviso_breve("Horneando… el progreso se ve en la barra inferior.")

    def _colocar(self) -> None:
        if self.id_pieza and ctl.colocar_pieza(self.sesion, self.id_pieza):
            self.app.refrescar("timeline", "monitor", "inspector", "mapa", "navegador")
            self.app.aviso_breve("Pieza colocada en el cabezal.")

    def _quitar_bruto(self) -> None:
        id_bruto = self.id_bruto
        if id_bruto is None:
            return

        def quitar() -> None:
            if ctl.quitar_bruto(self.sesion, id_bruto):
                self.id_bruto = None
                self.app.refrescar("taller", "navegador")

        self.app.confirmar("Quitar Bruto", "El Bruto se quitará del Taller (se puede deshacer); al guardar, "
                           "su archivo pasa a .papelera/.", quitar)

    def _quitar_pieza(self) -> None:
        id_pieza = self.id_pieza
        if id_pieza is None:
            return

        def quitar() -> None:
            if self.sesion.ejecutar(lambda: QuitarPieza(id_pieza)):
                self.id_pieza = None
                self.app.refrescar("taller", "navegador")

        self.app.confirmar("Quitar Pieza", "La Pieza se quitará del Taller (se puede deshacer).", quitar)

