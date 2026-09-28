"""Monitor con el lienzo, la vista previa y el control espacial.

Capas del monitor (de abajo hacia arriba):
    mesa de trabajo → imagen (niveles 2 y 4) o video (nivel 3) → canvas con
    lienzo, márgenes, guía 9:16 y asas → detector de gestos.

Reproducción:
- Si el pre-render del minuto está al día, se reproduce con `flet_video.Video`
  (nivel 3) y el cabezal sigue la posición del video.
- Si no, nivel 2: el audio del minuto (`flet_audio.Audio`) es el reloj maestro
  (`RelojAudio`) y cada tic compone un fotograma del banco en un hilo aparte.
  Mientras tanto se encarga el pre-render para la próxima vez.
"""

from __future__ import annotations

import asyncio
import time
import wave

import numpy as np
from typing import TYPE_CHECKING

import flet as ft
import flet.canvas as cv
import flet_audio
import flet_video

from editor.app.controladores import reproduccion
from editor.app.ui import asas
from editor.app.ui.tema import TEMA, texto_suave
from editor.app.ui.widgets import actualizar, timecode
from editor.app.ui.widgets.imagen import imagen_vacia
from editor.core.comandos import MoverAncla, PonerKeyframe, TransformarElemento
from editor.core.comandos.compuesto import ComandoCompuesto
from editor.core.espacio.geometria import Punto
from editor.core.espacio.transform import PROPIEDADES_ANIMABLES, Transform
from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO, FOTOGRAMAS_POR_MINUTO, FPS
from editor.core.modelo.keyframe import Keyframe
from editor.core.servicios.vista_previa import RelojAudio

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana

ANCHO_SENAL, ALTO_SENAL = 220, 110
ZOOMS_LIENZO = {"Encajar": 0.0, "25 %": 0.25, "50 %": 0.5, "100 %": 1.0, "200 %": 2.0}
INTERVALO_ARRASTRE = 0.1   # la imagen se refresca ~10 veces por segundo al arrastrar


async def _con_limite(corrutina, espera: float = 1.0, resultado=None):
    """Llamada a Audio/Video con tiempo máximo: sin salida de sonido o sin libmpv pueden no
    responder, y la reproducción no debe quedarse esperando. None si no respondió o falló;
    `resultado` sustituye al valor de las llamadas que no devuelven nada."""
    try:
        valor = await asyncio.wait_for(corrutina, timeout=espera)
    except Exception:  # noqa: BLE001 — incluye TimeoutError
        return None
    return resultado if valor is None else valor


class Monitor:
    def __init__(self, app: "Ventana") -> None:
        self.app = app
        self.vista = asas.VistaLienzo(960, 540)
        self.margenes = False
        self.guia_vertical = False
        self._ultima_imagen_f: int | None = None
        self._arrastre: dict | None = None
        self._generacion = 0
        # Los servicios de Flet se registran en la página al construirse: se crea aquí,
        # dentro del contexto de la página, y luego solo se le cambia `src`.
        self._audio = flet_audio.Audio(autoplay=False)
        self._video: flet_video.Video | None = None
        self._video_listo = asyncio.Event()
        self._nivel3 = True        # se desactiva si el reproductor de video falla una vez
        self._ultimo_alternar = 0.0
        self._audios_listos: dict[tuple[int, int, str | None], str] = {}

        self.imagen = ft.Image(src=imagen_vacia(), gapless_playback=True, fit=ft.BoxFit.FILL)
        self.lienzo = cv.Canvas(shapes=[], expand=True)
        self.gestos = ft.GestureDetector(
            content=self.lienzo,
            expand=True,
            drag_interval=16,
            hover_interval=50,
            on_tap_down=self._tocar,
            on_pan_start=self._empezar_arrastre,
            on_pan_update=self._arrastrar,
            on_pan_end=self._soltar,
            on_hover=self._pasar,
            on_scroll=self._rueda,
        )
        self.contenedor_video = ft.Container(visible=False)
        self.area = ft.Container(
            content=ft.Stack([self.imagen, self.contenedor_video, self.gestos], expand=True),
            bgcolor=TEMA.mesa,
            expand=True,
            on_size_change=self._redimensionar,
            size_change_interval=100,
        )
        self.tiempo = ft.TextField(
            value=timecode.formatear(0), width=110, dense=True, text_size=TEMA.tamano_texto,
            text_align=ft.TextAlign.CENTER, on_submit=self._ir_a_tiempo,
            on_focus=lambda _: app.enfocar("texto"), on_blur=lambda _: app.enfocar("monitor"),
        )
        self.boton_reproducir = ft.IconButton(ft.Icons.PLAY_ARROW, tooltip="Reproducir (Espacio)",
                                              on_click=lambda _: self.alternar_reproduccion())
        self.idioma = ft.Dropdown(
            width=110, dense=True, label="Escucha",
            options=[ft.DropdownOption(key=i, text=i) for i in app.sesion.proyecto.idiomas],
            value=app.sesion.estado.idioma_escucha, on_select=self._cambiar_idioma,
        )
        self.zoom = ft.Dropdown(
            width=120, dense=True, value="Encajar",
            options=[ft.DropdownOption(key=k, text=k) for k in ZOOMS_LIENZO], on_select=self._cambiar_zoom,
        )
        self.estado_texto = texto_suave("")
        # Medidores de nivel y monitores de señal.
        self.medidor = cv.Canvas(shapes=[], height=8, expand=True)
        self._pcm: dict[str, np.ndarray] = {}
        self.senal = cv.Canvas(shapes=[], height=ALTO_SENAL, width=2 * ANCHO_SENAL + 12)
        self.panel_senal = ft.Container(self.senal, visible=False, bgcolor=TEMA.panel_alto, padding=4)
        transporte = ft.Row(
            [
                ft.IconButton(ft.Icons.SKIP_PREVIOUS, tooltip="Inicio del minuto (PageUp: minuto anterior)",
                              on_click=lambda _: self.app.mover_cabezal_a(self.app.sesion.estado.minuto * FOTOGRAMAS_POR_MINUTO)),
                ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Fotograma anterior (←)",
                              on_click=lambda _: self.app.mover_cabezal(-1)),
                self.boton_reproducir,
                ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Fotograma siguiente (→)",
                              on_click=lambda _: self.app.mover_cabezal(1)),
                ft.IconButton(ft.Icons.SKIP_NEXT, tooltip="Minuto siguiente",
                              on_click=lambda _: self.app.mover_cabezal_a((self.app.sesion.estado.minuto + 1) * FOTOGRAMAS_POR_MINUTO)),
                self.tiempo,
                self.idioma,
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.CROP_FREE, tooltip="Márgenes seguros", on_click=self._alternar_margenes),
                ft.IconButton(ft.Icons.STAY_CURRENT_PORTRAIT, tooltip="Guía 9:16", on_click=self._alternar_guia),
                ft.IconButton(ft.Icons.MONITOR_HEART, tooltip="Señal: histograma y forma de onda de luminancia",
                              on_click=self._alternar_senal),
                self.zoom,
            ],
            spacing=2,
            height=44,
        )
        self.control = ft.Container(
            content=ft.Column([self.area, self.medidor, transporte, self.panel_senal, self.estado_texto],
                              spacing=2, expand=True),
            bgcolor=TEMA.panel,
            padding=4,
            expand=True,
        )

    # --- Estado ------------------------------------------------------------------------

    @property
    def sesion(self):
        return self.app.sesion

    def refrescar(self) -> None:
        """Tras mover el cabezal o editar: imagen rápida y, en pausa, la exacta."""
        self.tiempo.value = timecode.formatear(self.sesion.estado.cabezal)
        self.redibujar_superposicion()
        if not self.sesion.estado.reproduciendo:
            self._pedir_imagen()
            if self.panel_senal.visible:
                reproduccion.pedir_senal(self.sesion, self._dibujar_senal)

    def _pedir_imagen(self) -> None:
        def exacta(datos: bytes, f: int) -> None:
            if f == self.sesion.estado.cabezal and not self.sesion.estado.reproduciendo:
                self._mostrar(datos, f)

        def rapida(datos: bytes, f: int) -> None:
            if self.sesion.estado.reproduciendo:
                return
            self._mostrar(datos, f)
            if f == self.sesion.estado.cabezal and self._arrastre is None:
                reproduccion.pedir_imagen(self.sesion, exacta, exacta=True, ancho_monitor=self.vista.rect_lienzo.ancho)

        reproduccion.pedir_imagen(self.sesion, rapida)

    def _mostrar(self, datos: bytes, f: int) -> None:
        self._ultima_imagen_f = f
        self.imagen.src = datos
        self.imagen.visible = True
        actualizar(self.imagen)

    def _colocar_imagen(self) -> None:
        r = self.vista.rect_lienzo
        self.imagen.left, self.imagen.top, self.imagen.width, self.imagen.height = r.x, r.y, r.ancho, r.alto
        self.contenedor_video.left, self.contenedor_video.top = r.x, r.y
        self.contenedor_video.width, self.contenedor_video.height = r.ancho, r.alto

    def _redimensionar(self, evento: ft.LayoutSizeChangeEvent) -> None:
        self.vista = asas.VistaLienzo(evento.width, evento.height, self.vista.zoom)
        self._colocar_imagen()
        self.redibujar_superposicion()
        actualizar(self.area)

    # --- Superposición -----------------------------------------------------------------

    def _contorno(self, elemento) -> asas.Contorno:
        carpeta = self.sesion.proyecto.raiz / "recursos" / "fuentes"
        return asas.Contorno.de(elemento, self.sesion.estado.cabezal, asas.tamano_natural(elemento, carpeta))

    def _ventana_short(self):
        """En el espacio Shorts, el encuadre del Short elegido (el que se arrastra, si se arrastra)."""
        if self.sesion.estado.espacio_trabajo != "shorts":
            return None
        return self.app.shorts.encuadre()

    def _seleccion_visual(self):
        elemento = self.sesion.seleccionado()
        if elemento is None or not elemento.es_visual or not elemento.contiene(self.sesion.estado.cabezal):
            return None
        return elemento

    def redibujar_superposicion(self, contorno_vivo: asas.Contorno | None = None) -> None:
        formas = asas.formas_lienzo(self.vista, self.margenes, self.guia_vertical, self._ventana_short())
        elemento = self._seleccion_visual()
        if contorno_vivo is not None:
            formas += asas.formas_contorno(contorno_vivo, self.vista)
        elif elemento is not None:
            editable = self.sesion.capitulo.editable(elemento)
            formas += asas.formas_contorno(self._contorno(elemento), self.vista, con_asas=editable)
        self.lienzo.shapes = formas
        actualizar(self.lienzo)

    # --- Gestos ------------------------------------------------------------------------

    def _tocar(self, evento: ft.TapEvent) -> None:
        self.app.enfocar("monitor")
        if evento.local_position is None or self.sesion.estado.reproduciendo:
            return
        x, y = evento.local_position.x, evento.local_position.y
        actual = self._seleccion_visual()
        if actual is not None and asas.asa_en(self._contorno(actual), self.vista, x, y) is not None:
            return
        elemento = self._elemento_bajo(x, y)
        self.app.seleccionar({elemento.id} if elemento is not None else set())

    def _elemento_bajo(self, x: float, y: float):
        """El Elemento visible más alto bajo el puntero."""
        punto = self.vista.a_lienzo(x, y)
        for elemento in reversed(self.sesion.capitulo.visuales_activos_en(self.sesion.estado.cabezal)):
            if asas.dentro(self._contorno(elemento).esquinas, punto):
                return elemento
        return None

    def _empezar_arrastre(self, evento: ft.DragStartEvent) -> None:
        if self.sesion.estado.reproduciendo:
            return
        x, y = evento.local_position.x, evento.local_position.y
        elemento = self._seleccion_visual()
        asa = asas.asa_en(self._contorno(elemento), self.vista, x, y) if elemento is not None else None
        if asa is None:
            # Arrastrar fuera de la selección: elige lo que hay debajo y lo mueve.
            elemento = self._elemento_bajo(x, y)
            if elemento is None:
                return
            self.app.seleccionar({elemento.id}, refrescar=False)
            asa = asas.MOVER
        if not self.sesion.capitulo.editable(elemento):
            return
        contorno = self._contorno(elemento)
        self._arrastre = {
            "id": elemento.id, "asa": asa, "original": contorno, "desde": self.vista.a_lienzo(x, y),
            "transform": contorno.transform, "ultimo": 0.0,
            "animadas": {p for p in PROPIEDADES_ANIMABLES if elemento.animacion.tiene(p)},
            "otros": [self._contorno(e).rect for e in self.sesion.capitulo.visuales_activos_en(self.sesion.estado.cabezal)
                      if e.id != elemento.id],
        }

    def _arrastrar(self, evento: ft.DragUpdateEvent) -> None:
        arrastre = self._arrastre
        if arrastre is None or evento.local_position is None:
            return
        hasta = self.vista.a_lienzo(evento.local_position.x, evento.local_position.y)
        original: asas.Contorno = arrastre["original"]
        if arrastre["asa"] == asas.ANCLA:
            ancla = original.transform.mover_ancla(*asas.ancla_local(original, hasta))
            arrastre["transform"] = ancla
            self.redibujar_superposicion(asas.Contorno.con_transform(ancla, original.tamano))
            return
        nuevo = asas.arrastrar(arrastre["asa"], original, arrastre["desde"], hasta, self.vista,
                               libre=self.app.shift_presionado, iman=self.sesion.estado.iman, otros=arrastre["otros"])
        arrastre["transform"] = nuevo
        self.redibujar_superposicion(asas.Contorno.con_transform(nuevo, original.tamano))
        self._mostrar_estado(hasta, nuevo)
        # Sin keyframes en juego: se aplica en vivo (se fusiona en un solo paso de deshacer).
        if not self._propiedades_animadas_cambiadas(arrastre, nuevo) and time.monotonic() - arrastre["ultimo"] >= INTERVALO_ARRASTRE:
            arrastre["ultimo"] = time.monotonic()
            if self._aplicar(arrastre, nuevo, avisar=False):
                self._pedir_imagen()

    def _soltar(self, _evento) -> None:
        arrastre, self._arrastre = self._arrastre, None
        if arrastre is None:
            return
        if arrastre["asa"] == asas.ANCLA:
            t: Transform = arrastre["transform"]
            self.sesion.ejecutar(lambda: MoverAncla(self.sesion.estado.capitulo, arrastre["id"], t.ancla_x, t.ancla_y))
        else:
            self._aplicar(arrastre, arrastre["transform"])
        self.app.refrescar("monitor", "inspector")

    def _propiedades_animadas_cambiadas(self, arrastre: dict, nuevo: Transform) -> set[str]:
        original: Transform = arrastre["original"].transform
        return {p for p in arrastre["animadas"] if abs(getattr(nuevo, p) - getattr(original, p)) > 1e-9}

    def _aplicar(self, arrastre: dict, nuevo: Transform, avisar: bool = True) -> bool:
        """Propiedades sin keyframes → la base del Elemento; con keyframes → keyframe en el cabezal."""
        sesion = self.sesion
        elemento = sesion.capitulo.buscar(arrastre["id"])
        if elemento is None:
            return False
        original: Transform = arrastre["original"].transform
        cambiadas = {p for p in PROPIEDADES_ANIMABLES if abs(getattr(nuevo, p) - getattr(original, p)) > 1e-9}
        if not cambiadas:
            return False
        base = elemento.espacio.con(**{p: getattr(nuevo, p) for p in cambiadas - arrastre["animadas"]})
        capitulo = sesion.estado.capitulo
        comandos = []
        if base != elemento.espacio:
            comandos.append(TransformarElemento(capitulo, elemento.id, base))
        f_local = sesion.estado.cabezal - elemento.inicio
        for propiedad in sorted(cambiadas & arrastre["animadas"]):
            previo = elemento.animacion.pista(propiedad).obtener(f_local)
            curva = previo.curva if previo is not None else "lineal"
            comandos.append(PonerKeyframe(capitulo, elemento.id, propiedad,
                                          Keyframe(f_local, float(getattr(nuevo, propiedad)), curva)))
        if not comandos:
            return False
        comando = comandos[0] if len(comandos) == 1 else ComandoCompuesto("Transformar", comandos)
        if avisar:
            return sesion.ejecutar(comando)
        antes = sesion.avisar
        sesion.avisar = lambda _texto: None
        try:
            return sesion.ejecutar(comando)
        finally:
            sesion.avisar = antes

    def _pasar(self, evento: ft.HoverEvent) -> None:
        if evento.local_position is None or self._arrastre is not None:
            return
        self._mostrar_estado(self.vista.a_lienzo(evento.local_position.x, evento.local_position.y))

    def _mostrar_estado(self, punto: Punto, transform: Transform | None = None) -> None:
        partes = [f"cursor: ({punto.x:.0f}, {punto.y:.0f}) px", f"zoom: {self.vista.factor * 100:.0f} %"]
        if transform is not None:
            partes.append(f"x {transform.x:.0f} · y {transform.y:.0f} · escala {transform.escala_x:.2f}×{transform.escala_y:.2f}"
                          f" · rot {transform.rotacion:.1f}°")
        self.estado_texto.value = "   ".join(partes)
        actualizar(self.estado_texto)

    def _rueda(self, evento: ft.ScrollEvent) -> None:
        if evento.scroll_delta is None or evento.scroll_delta.y == 0:
            return
        factor = self.vista.factor * (1.1 if evento.scroll_delta.y < 0 else 1 / 1.1)
        self.vista = asas.VistaLienzo(self.vista.area_ancho, self.vista.area_alto, max(0.05, min(8.0, factor)))
        self.zoom.value = None
        self._colocar_imagen()
        self.redibujar_superposicion()
        actualizar(self.area)

    def mover_seleccion(self, direccion: str, pixeles: float) -> None:
        """Alt + flechas: 1 px; Alt + Shift + flechas: 10 px."""
        elemento = self._seleccion_visual()
        if elemento is None or not self.sesion.capitulo.editable(elemento):
            return
        contorno = self._contorno(elemento)
        arrastre = {"id": elemento.id, "original": contorno,
                    "animadas": {p for p in PROPIEDADES_ANIMABLES if elemento.animacion.tiene(p)}}
        if self._aplicar(arrastre, asas.mover_teclado(contorno.transform, direccion, pixeles)):
            self.app.refrescar("monitor", "inspector")

    # --- Controles ---------------------------------------------------------------------

    def _ir_a_tiempo(self, _evento) -> None:
        f = timecode.interpretar(self.tiempo.value or "")
        if f is None:
            self.app.avisar("Tiempo inválido: use MM:SS.FF")
            return
        self.app.mover_cabezal_a(f)

    def _cambiar_idioma(self, evento) -> None:
        self.sesion.estado.idioma_escucha = evento.control.value
        self.app.refrescar("mapa")

    def _cambiar_zoom(self, evento) -> None:
        self.vista = asas.VistaLienzo(self.vista.area_ancho, self.vista.area_alto, ZOOMS_LIENZO.get(evento.control.value, 0.0))
        self._colocar_imagen()
        self.redibujar_superposicion()

    def _alternar_margenes(self, _evento) -> None:
        self.margenes = not self.margenes
        self.redibujar_superposicion()

    def _alternar_guia(self, _evento) -> None:
        self.guia_vertical = not self.guia_vertical
        self.redibujar_superposicion()

    # --- Reproducción ------------------------------------------------------------------

    def alternar_reproduccion(self) -> None:
        # Con el botón de reproducir enfocado, Espacio llega dos veces (el botón y el atajo):
        # dos pulsaciones en menos de 0,25 s cuentan como una.
        ahora = time.monotonic()
        if ahora - self._ultimo_alternar < 0.25:
            return
        self._ultimo_alternar = ahora
        if self.sesion.estado.reproduciendo:
            self.detener()
        else:
            self.sesion.estado.reproduciendo = True
            self._generacion += 1
            self.boton_reproducir.icon = ft.Icons.PAUSE
            self.app.page.run_task(self._reproducir, self._generacion)

    def detener(self) -> None:
        if not self.sesion.estado.reproduciendo:
            return
        self.sesion.estado.reproduciendo = False
        self._generacion += 1
        self.boton_reproducir.icon = ft.Icons.PLAY_ARROW
        self.app.page.run_task(self._parar_medios)
        self.imagen.visible = True
        self.contenedor_video.visible = False
        self.app.refrescar("monitor", "timeline")

    async def _parar_medios(self) -> None:
        try:
            if self._audio.src:
                await _con_limite(self._audio.pause())
            if self._video is not None:
                await _con_limite(self._video.pause())
        except Exception:  # noqa: BLE001 — el reproductor pudo haberse cerrado
            pass

    def _sigue(self, generacion: int) -> bool:
        return self.sesion.estado.reproduciendo and generacion == self._generacion

    async def _reproducir(self, generacion: int) -> None:
        try:
            while self._sigue(generacion):
                if self.sesion.estado.cabezal >= FOTOGRAMAS_POR_CAPITULO - 1:
                    break
                minuto = self.sesion.estado.minuto
                ruta = reproduccion.prerender_listo(self.sesion, minuto) if self._nivel3 else None
                if ruta is not None:
                    continuar = await self._reproducir_video(str(ruta), minuto, generacion)
                    if continuar is None:
                        # El reproductor de video no funcionó (p. ej. falta libmpv): se sigue en vivo.
                        self._nivel3 = False
                        self.app.aviso_breve("La reproducción fluida no está disponible (¿falta libmpv?): se usa la vista en vivo.")
                        continuar = await self._reproducir_vivo(minuto, generacion)
                else:
                    reproduccion.preparar_minuto(self.sesion, minuto,
                                                 lambda _r: self.app.refrescar("mapa"))
                    continuar = await self._reproducir_vivo(minuto, generacion)
                if not continuar or not self.sesion.estado.seguir_cabezal:
                    break
        except Exception as error:  # noqa: BLE001 — un fallo de reproducción no debe cerrar la app
            self.app.avisar(f"Reproducción detenida: {error}")
        if generacion == self._generacion:
            self.detener()
            actualizar(self.app.page)

    async def _reproducir_vivo(self, minuto: int, generacion: int) -> bool:
        """Nivel 2 con el audio del minuto como reloj. Devuelve True si llegó al final del minuto."""
        sesion = self.sesion
        inicio, fin = minuto * FOTOGRAMAS_POR_MINUTO, (minuto + 1) * FOTOGRAMAS_POR_MINUTO
        reloj = RelojAudio(fotograma_base=sesion.estado.cabezal)
        reloj.sincronizar(0.0, True)
        periodo = 1 / max(1, min(FPS, sesion.ajustes.vista_previa_fps))
        clave = (sesion.estado.capitulo, minuto, sesion.estado.idioma_escucha)
        audio_sonando = False
        ultimo_sincronizado = 0.0
        ultima_posicion = -1.0

        if clave not in self._audios_listos:
            reproduccion.audio_del_minuto(sesion, minuto, lambda ruta: self._audios_listos.__setitem__(clave, str(ruta)))

        while self._sigue(generacion):
            momento = time.monotonic()
            if not audio_sonando and clave in self._audios_listos:
                # El audio llegó: pasa a ser el reloj desde la posición actual.
                desplazamiento = (reloj.fotograma() - inicio) / FPS
                audio_sonando = True   # se intenta una vez; si no responde, manda el reloj monotónico
                if await self._sonar(self._audios_listos[clave], desplazamiento):
                    desplazamiento = (reloj.fotograma() - inicio) / FPS
                    reloj.fotograma_base = inicio
                    reloj.sincronizar(desplazamiento, True)
                    ultima_posicion = desplazamiento
            elif audio_sonando and momento - ultimo_sincronizado > 0.5:
                posicion = await _con_limite(self._audio.get_current_position())
                segundos = None if posicion is None else posicion.in_milliseconds / 1000
                # Solo manda el audio si de verdad avanza (sin salida de sonido la posición
                # se queda quieta y frenaría la imagen): si no, sigue el reloj monotónico.
                if segundos is not None and segundos > ultima_posicion:
                    reloj.sincronizar(segundos, True)
                    ultima_posicion = segundos
                ultimo_sincronizado = momento
            f = reloj.fotograma()
            if f >= fin:
                sesion.ir_a(fin)
                return True
            sesion.ir_a(f)
            self._medir(self._audios_listos.get(clave), f - inicio)
            copia = reproduccion.instantanea_en(sesion, f)
            datos = await asyncio.to_thread(reproduccion.fotograma_en_vivo, sesion, copia, f)
            if not self._sigue(generacion):
                break
            self.imagen.src = datos
            self.tiempo.value = timecode.formatear(f)
            self.app.cabezal_movido(ligero=True)
            actualizar(self.app.page)
            await asyncio.sleep(max(0.0, periodo - (time.monotonic() - momento)))
        return False

    # --- Medidores y señal ---------------------------------------------------------------

    def _medir(self, ruta: str | None, f_local: float) -> None:
        """Pico por canal en 50 ms alrededor del instante (del WAV del minuto)."""
        if ruta is None:
            return
        if ruta not in self._pcm:
            if len(self._pcm) > 4:
                self._pcm.clear()
            try:
                with wave.open(ruta, "rb") as archivo:
                    datos = np.frombuffer(archivo.readframes(archivo.getnframes()), dtype="<i2")
                self._pcm[ruta] = datos.reshape(-1, 2).astype(np.float32) / 32768
            except (OSError, wave.Error, ValueError):
                self._pcm[ruta] = np.zeros((0, 2), dtype=np.float32)
        pcm = self._pcm[ruta]
        centro = int(f_local / FPS * 48000)
        trozo = pcm[max(0, centro - 1200): centro + 1200]
        picos = np.abs(trozo).max(axis=0) if len(trozo) else np.zeros(2)
        ancho = max(10.0, self.vista.area_ancho)
        formas: list[cv.Shape] = [cv.Rect(0, 0, ancho, 8, paint=ft.Paint(color=TEMA.panel_alto))]
        for canal, pico in enumerate(picos):
            db = 20 * np.log10(max(float(pico), 1e-5))
            fraccion = max(0.0, min(1.0, (db + 60) / 60))
            color = TEMA.error if db > -1 else (TEMA.marcador if db > -9 else TEMA.render_al_dia)
            formas.append(cv.Rect(0, canal * 4, ancho * fraccion, 3, paint=ft.Paint(color=color)))
        self.medidor.shapes = formas

    def _alternar_senal(self, _evento) -> None:
        self.panel_senal.visible = not self.panel_senal.visible
        if self.panel_senal.visible:
            reproduccion.pedir_senal(self.sesion, self._dibujar_senal)
        actualizar(self.control)

    def _dibujar_senal(self, datos: dict) -> None:
        """Izquierda: histograma RGB; derecha: forma de onda de luminancia (0 abajo, 255 arriba)."""
        formas: list[cv.Shape] = [cv.Rect(0, 0, ANCHO_SENAL, ALTO_SENAL, paint=ft.Paint(color=TEMA.lienzo)),
                                  cv.Rect(ANCHO_SENAL + 12, 0, ANCHO_SENAL, ALTO_SENAL, paint=ft.Paint(color=TEMA.lienzo))]
        for histograma, color in zip(datos["histogramas"], ("#ff5555", "#55ff55", "#5599ff")):
            paso = ANCHO_SENAL / len(histograma)
            puntos = [cv.Path.MoveTo(0, ALTO_SENAL)]
            puntos += [cv.Path.LineTo(i * paso, ALTO_SENAL - v * (ALTO_SENAL - 4)) for i, v in enumerate(histograma)]
            formas.append(cv.Path(puntos, paint=ft.Paint(color=ft.Colors.with_opacity(0.8, color), stroke_width=1.2,
                                                         style=ft.PaintingStyle.STROKE)))
        onda = datos["onda"]
        columnas, niveles = len(onda), len(onda[0]) if onda else 1
        bandas = {0.15: [], 0.4: [], 0.75: []}
        for c, columna in enumerate(onda):
            x = ANCHO_SENAL + 12 + (c + 0.5) * ANCHO_SENAL / columnas
            for n, valor in enumerate(columna):
                for umbral in sorted(bandas, reverse=True):
                    if valor >= umbral:
                        y = ALTO_SENAL - (n + 0.5) * ALTO_SENAL / niveles
                        bandas[umbral] += [cv.Path.MoveTo(x, y - 1), cv.Path.LineTo(x, y + 1)]
                        break
        for umbral, trazos in bandas.items():
            if trazos:
                formas.append(cv.Path(trazos, paint=ft.Paint(color=ft.Colors.with_opacity(min(1.0, umbral + 0.2), "#9fe8a0"),
                                                             stroke_width=2, style=ft.PaintingStyle.STROKE)))
        self.senal.shapes = formas
        actualizar(self.senal)

    async def _sonar(self, ruta: str, segundos: float) -> bool:
        if self._audio.src != ruta:
            self._audio.src = ruta
            self._audio.update()
        return await _con_limite(self._audio.play(ft.Duration(milliseconds=int(segundos * 1000))), resultado=True) is True

    async def _reproducir_video(self, ruta: str, minuto: int, generacion: int) -> bool | None:
        """Nivel 3: el pre-render del minuto con su audio.

        Devuelve True al llegar al final del minuto, False si se detuvo y None si el
        reproductor de video no funcionó (entonces el cabezal queda donde estaba).
        """
        sesion = self.sesion
        inicio, fin = minuto * FOTOGRAMAS_POR_MINUTO, (minuto + 1) * FOTOGRAMAS_POR_MINUTO
        self._video_listo.clear()
        terminado = asyncio.Event()
        clave_audio = (sesion.estado.capitulo, minuto, sesion.estado.idioma_escucha)
        if clave_audio not in self._audios_listos:   # solo para los medidores de nivel
            reproduccion.audio_del_minuto(sesion, minuto,
                                          lambda ruta: self._audios_listos.__setitem__(clave_audio, str(ruta)))
        fallo = asyncio.Event()
        self._video = flet_video.Video(
            playlist=[flet_video.VideoMedia(ruta)], autoplay=False, controls=False,
            fill_color=TEMA.lienzo, expand=True,
            on_load=lambda _: self._video_listo.set(), on_complete=lambda _: terminado.set(),
            on_error=lambda _: fallo.set(),
        )
        self.contenedor_video.content = self._video
        self.contenedor_video.visible = True
        self.imagen.visible = False
        self.app.page.update()

        def volver_a_imagen() -> None:
            self.contenedor_video.visible = False
            self.contenedor_video.content = None
            self.imagen.visible = True

        try:
            await asyncio.wait_for(self._video_listo.wait(), timeout=3)
        except asyncio.TimeoutError:
            volver_a_imagen()
            return None
        f = sesion.estado.cabezal
        if await _con_limite(self._video.seek(ft.Duration(milliseconds=int((f - inicio) / FPS * 1000))),
                             resultado=True) is None or await _con_limite(self._video.play(), resultado=True) is None:
            volver_a_imagen()
            return None
        while self._sigue(generacion) and not terminado.is_set() and not fallo.is_set():
            await asyncio.sleep(0.1)
            posicion = await _con_limite(self._video.get_current_position())
            if posicion is None:
                fallo.set()
                break
            f = inicio + int(posicion.in_milliseconds / 1000 * FPS)
            if f >= fin - 1:
                break
            sesion.ir_a(f)
            self._medir(self._audios_listos.get(clave_audio), f - inicio)
            self.tiempo.value = timecode.formatear(f)
            self.app.cabezal_movido(ligero=True)
            self.app.page.update()
        if fallo.is_set() or (terminado.is_set() and f < fin - FPS):
            volver_a_imagen()   # terminó antes de tiempo: el video no se reprodujo de verdad
            return None
        if not self._sigue(generacion):
            return False
        sesion.ir_a(fin)
        volver_a_imagen()
        return True
