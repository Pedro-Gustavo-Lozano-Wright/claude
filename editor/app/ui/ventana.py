"""Ventana de un proyecto abierto: secciones, espacios de trabajo y órdenes (E12).

Es el único lugar que conoce todos los paneles. Los paneles piden cosas a la
ventana (mover el cabezal, seleccionar, refrescar partes) y la ventana:

- agrupa los redibujados: como mucho uno por cuadro (`refrescar`);
- escucha el bus (los eventos de tareas llegan de otros hilos y
  `Sesion.escuchar` los pasa al bucle de Flet);
- traduce el teclado a acciones según el foco (`teclado.py`);
- guarda, autoguarda y cierra con los diálogos de PROJECT.md 22.6.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

import flet as ft

from editor.app.controladores import proyecto as ctl_proyecto
from editor.app.controladores import reproduccion
from editor.app.controladores import taller as ctl_taller
from editor.app.controladores import timeline as ctl_timeline
from editor.app.estado import ESPACIOS, ZOOMS, Sesion
from editor.app.ui.cola_render import BarraTareas, ColaRender
from editor.app.ui.distribucion import Distribucion
from editor.app.ui.divisor import Divisor
from editor.app.ui.inspector import Inspector
from editor.app.ui.mapa_capitulo import MapaCapitulo
from editor.app.ui.monitor import Monitor
from editor.app.ui.navegador import Navegador
from editor.app.ui.taller import Taller
from editor.app.ui.teclado import Teclado
from editor.app.ui.tema import TEMA, texto, texto_suave
from editor.app.ui.widgets import actualizar
from editor.app.ui.timeline import Timeline
from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO, FOTOGRAMAS_POR_MINUTO, FPS, MINUTOS_POR_CAPITULO
from editor.core.eventos import (
    BancoListo,
    BrutoImportado,
    CapituloCreado,
    ElementoCambiado,
    HistorialCambiado,
    MedioFueraDeLinea,
    PiezaHorneada,
    PiezaModificada,
    ProyectoGuardado,
    RenderTerminado,
)

if TYPE_CHECKING:
    from editor.app.aplicacion import Aplicacion

TODAS = ("barra", "navegador", "monitor", "inspector", "mapa", "timeline", "taller", "render", "tareas")
NOMBRES_ESPACIO = {"taller": "Taller", "minuto": "Minuto", "capitulo": "Capítulo", "shorts": "Shorts", "render": "Render"}
ESPERA_PRERENDER = 3.0      # segundos sin editar antes de preparar la vista previa del minuto
INTERVALO_AUTOSAVE = 10.0   # cada cuánto se consulta si toca autoguardar


class Ventana:
    def __init__(self, raiz: "Aplicacion", sesion: Sesion) -> None:
        self.raiz = raiz
        self.page: ft.Page = raiz.page
        self.sesion = sesion
        self.selector = raiz.selector
        self.distribucion = Distribucion()
        self._pendientes: set[str] = set()
        self._programado = False
        self._abierta = True
        self._suscripciones: list[Callable[[], None]] = []
        self._teclas: set[str] = set()
        self._minuto_visto = sesion.estado.minuto
        self._ultima_edicion = 0.0

        sesion.avisar = self.avisar
        sesion.estado.espacio_trabajo = self.distribucion.activo

        self.navegador = Navegador(self)
        self.monitor = Monitor(self)
        self.inspector = Inspector(self)
        self.mapa = MapaCapitulo(self)
        self.timeline = Timeline(self)
        self.taller = Taller(self)
        self.cola_render = ColaRender(self)
        self.barra_tareas = BarraTareas(self)
        self._paneles = {
            "navegador": self.navegador, "monitor": self.monitor, "inspector": self.inspector, "mapa": self.mapa,
            "timeline": self.timeline, "taller": self.taller, "render": self.cola_render, "tareas": self.barra_tareas,
        }

        self.teclado = Teclado(lambda: self.sesion.estado.foco)
        self._registrar_atajos()

        self.titulo = texto("", weight=ft.FontWeight.BOLD)
        self.boton_deshacer = ft.IconButton(ft.Icons.UNDO, tooltip="Deshacer (Ctrl+Z)", on_click=lambda _: self.deshacer())
        self.boton_rehacer = ft.IconButton(ft.Icons.REDO, tooltip="Rehacer (Ctrl+Shift+Z)", on_click=lambda _: self.rehacer())
        self.boton_guardar = ft.IconButton(ft.Icons.SAVE, tooltip="Guardar (Ctrl+S)", on_click=lambda _: self.guardar())
        self.espacios = ft.SegmentedButton(
            segments=[ft.Segment(value=e, label=ft.Text(NOMBRES_ESPACIO[e])) for e in ESPACIOS],
            selected=[self.distribucion.activo],
            allow_multiple_selection=False,
            show_selected_icon=False,
            on_change=self._cambiar_espacio,
        )
        barra = ft.Container(
            content=ft.Row([
                self.titulo,
                ft.Container(expand=True),
                self.espacios,
                ft.Container(expand=True),
                self.boton_deshacer, self.boton_rehacer, self.boton_guardar,
                ft.IconButton(ft.Icons.RESTART_ALT, tooltip="Restablecer la distribución de este espacio",
                              on_click=lambda _: self._restablecer_distribucion()),
                ft.IconButton(ft.Icons.CLOSE, tooltip="Cerrar el proyecto", on_click=lambda _: self.pedir_cierre()),
            ], height=44),
            bgcolor=TEMA.panel_alto,
            padding=ft.Padding.symmetric(horizontal=8),
        )
        self.cuerpo = ft.Container(expand=True)
        # KeyboardListener sigue Shift/Ctrl para los gestos; no admite `expand`, por eso va dentro de un Container.
        self.control = ft.Container(
            ft.KeyboardListener(
                content=ft.Column([barra, self.cuerpo, self.barra_tareas.control], spacing=0, expand=True),
                autofocus=True,
                on_key_down=self._tecla_abajo,
                on_key_up=self._tecla_arriba,
            ),
            expand=True,
        )
        self._escuchar_bus()
        self._componer()

    # --- Ciclo de vida -----------------------------------------------------------------

    def montar(self) -> None:
        self.page.on_keyboard_event = self._teclado
        self.page.controls.clear()
        self.page.add(self.control)
        self.refrescar(*TODAS)
        self.page.run_task(self._bucle_autosave)
        self.page.run_task(self._bucle_prerender)

    def desmontar(self) -> None:
        self.monitor.detener()
        self.page.on_keyboard_event = None
        self.abandonar()

    def abandonar(self) -> None:
        """Libera la sesión sin tocar la interfaz (también si la conexión ya se perdió)."""
        self._abierta = False
        for cancelar in self._suscripciones:
            cancelar()
        self._suscripciones.clear()
        ctl_taller.cerrar_visor()
        self.distribucion.guardar()
        self.sesion.cerrar()

    def escuchar(self, tipo, manejador) -> None:
        self._suscripciones.append(self.sesion.escuchar(tipo, manejador))

    def _escuchar_bus(self) -> None:
        def edicion(evento: ElementoCambiado) -> None:
            import time

            self._ultima_edicion = time.monotonic()
            self.refrescar("timeline", "monitor", "inspector", "mapa")

        self.escuchar(ElementoCambiado, edicion)
        self.escuchar(HistorialCambiado, lambda _e: self.refrescar(*TODAS))
        self.escuchar(BrutoImportado, lambda _e: self.refrescar("navegador", "taller"))
        self.escuchar(PiezaModificada, lambda _e: self.refrescar("navegador", "taller"))
        self.escuchar(PiezaHorneada, lambda _e: self.refrescar("navegador", "taller", "timeline", "monitor", "mapa"))
        self.escuchar(BancoListo, lambda _e: self.refrescar("monitor", "timeline"))
        self.escuchar(ProyectoGuardado, lambda _e: self.refrescar("barra", "mapa"))
        self.escuchar(RenderTerminado, lambda _e: self.refrescar("render", "mapa"))
        self.escuchar(CapituloCreado, lambda _e: self.refrescar("navegador"))
        self.escuchar(MedioFueraDeLinea, lambda e: self.aviso_breve(f"Medio fuera de línea: {e.ruta}"))

    # --- Redibujado agrupado -----------------------------------------------------------

    def refrescar(self, *partes: str) -> None:
        """Marca partes para redibujar; se redibujan juntas en el próximo cuadro."""
        self._pendientes.update(partes or TODAS)
        if not self._programado and self._abierta:
            self._programado = True
            self.page.run_task(self._redibujar)

    async def _redibujar(self) -> None:
        await asyncio.sleep(1 / 60)
        partes, self._pendientes = self._pendientes, set()
        self._programado = False
        if not self._abierta:
            return
        if "barra" in partes:
            self._barra()
        for nombre in ("navegador", "mapa", "timeline", "inspector", "taller", "render", "tareas", "monitor"):
            if nombre in partes:
                try:
                    self._paneles[nombre].refrescar()
                except Exception:  # noqa: BLE001 — un panel no debe tumbar la ventana
                    import logging

                    logging.getLogger(__name__).exception("Error al redibujar %s", nombre)
        actualizar(self.page)

    def _barra(self) -> None:
        historial = self.sesion.historial
        proyecto = self.sesion.proyecto
        cambios = " •" if historial.hay_cambios else ""
        lectura = " (solo lectura)" if self.sesion.solo_lectura else ""
        self.titulo.value = f"{proyecto.nombre}{lectura}{cambios}"
        self.page.title = f"{proyecto.nombre}{cambios} — Editor"
        self.boton_deshacer.disabled = not historial.puede_deshacer
        self.boton_rehacer.disabled = not historial.puede_rehacer
        self.boton_guardar.disabled = self.sesion.solo_lectura

    # --- Distribución ------------------------------------------------------------------

    def _componer(self) -> None:
        espacio = self.distribucion.actual
        nombre = self.distribucion.activo

        def lateral(panel: str, control: ft.Control, izquierda: bool) -> list[ft.Control]:
            if not espacio.visible(panel):
                return []
            caja = ft.Container(control, width=espacio.tamano(panel))
            divisor = Divisor(
                vertical=True,
                al_mover=lambda d: self._ajustar(panel, d if izquierda else -d, caja, "width"),
                al_soltar=self.distribucion.guardar,
                al_plegar=lambda: self._plegar(panel),
            ).control
            return [caja, divisor] if izquierda else [divisor, caja]

        def franja(panel: str, control: ft.Control) -> list[ft.Control]:
            if not espacio.visible(panel):
                return []
            caja = ft.Container(control, height=espacio.tamano(panel))
            divisor = Divisor(
                vertical=False,
                al_mover=lambda d: self._ajustar(panel, -d, caja, "height"),
                al_soltar=self.distribucion.guardar,
                al_plegar=lambda: self._plegar(panel),
            ).control
            return [divisor, caja]

        if nombre == "taller":
            superior: ft.Control = ft.Row([ft.Container(self.taller.control, expand=True),
                                           ft.Container(self.monitor.control, expand=True)], spacing=4, expand=True)
        elif nombre == "shorts":
            superior = ft.Column([
                ft.Container(self.monitor.control, expand=True),
                texto_suave("Espacio Shorts: la ventana 9:16 y su vista previa vertical llegan en la épica E20. "
                            "La guía 9:16 del monitor ya muestra qué entra en un Short."),
            ], expand=True)
        else:
            superior = self.monitor.control
        centro: list[ft.Control] = [ft.Container(superior, expand=True)]
        centro += franja("mapa", self.mapa.control)
        if nombre == "render" or espacio.visible("cola_render"):
            centro += [ft.Divider(height=4), ft.Container(self.cola_render.control, height=max(220, espacio.tamano("timeline")))]
        else:
            centro += franja("timeline", self.timeline.control)
        fila = (lateral("navegador", self.navegador.control, True)
                + [ft.Column(centro, spacing=0, expand=True)]
                + lateral("inspector", self.inspector.control, False))
        self.cuerpo.content = ft.Row(fila, spacing=0, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)

    def _ajustar(self, panel: str, delta: float, caja: ft.Container, medida: str) -> None:
        espacio = self.distribucion.actual
        espacio.ajustar(panel, delta)
        setattr(caja, medida, espacio.tamano(panel))
        actualizar(caja)

    def _plegar(self, panel: str) -> None:
        self.distribucion.actual.alternar_plegado(panel)
        self._componer()
        self.distribucion.guardar()
        self.refrescar(*TODAS)

    def _restablecer_distribucion(self) -> None:
        self.distribucion.restablecer()
        self.distribucion.guardar()
        self._componer()
        self.refrescar(*TODAS)

    def _cambiar_espacio(self, evento) -> None:
        seleccion = list(evento.control.selected or [])
        if seleccion:
            self.cambiar_espacio(seleccion[0])

    def cambiar_espacio(self, nombre: str) -> None:
        if nombre not in ESPACIOS:
            return
        self.distribucion.cambiar(nombre)
        self.espacios.selected = [nombre]
        estado = self.sesion.estado
        estado.espacio_trabajo = nombre
        if nombre == "capitulo":
            estado.zoom_timeline = "capitulo"
        elif nombre == "minuto" and estado.zoom_timeline == "capitulo":
            estado.zoom_timeline = "minuto"
        estado.foco = "taller" if nombre == "taller" else "timeline"
        self._componer()
        self.distribucion.guardar()
        self.refrescar(*TODAS)

    # --- Órdenes que usan los paneles -------------------------------------------------

    @property
    def shift_presionado(self) -> bool:
        return bool(self._teclas & {"Shift Left", "Shift Right", "Shift"})

    @property
    def ctrl_presionado(self) -> bool:
        return bool(self._teclas & {"Control Left", "Control Right", "Control", "Meta Left", "Meta Right"})

    def enfocar(self, foco: str) -> None:
        self.sesion.estado.foco = foco

    def seleccionar(self, ids: set[str], refrescar: bool = True) -> None:
        self.sesion.estado.seleccion = set(ids)
        if refrescar:
            self.refrescar("timeline", "monitor", "inspector")

    def mover_cabezal(self, delta: int) -> None:
        self.mover_cabezal_a(self.sesion.estado.cabezal + delta)

    def mover_cabezal_a(self, f: int) -> None:
        if self.sesion.estado.reproduciendo:
            self.monitor.detener()
        self.sesion.ir_a(f)
        self.cabezal_movido()

    def cabezal_movido(self, ligero: bool = False) -> None:
        """Tras mover el cabezal. `ligero` (reproducción): solo la línea del cabezal y el tiempo."""
        minuto = self.sesion.estado.minuto
        cambio_minuto = minuto != self._minuto_visto
        self._minuto_visto = minuto
        partes: list[str] = []
        if self.timeline.necesita_redibujo_por_cabezal() or cambio_minuto:
            partes += ["timeline", "mapa", "navegador"]
        else:
            self.timeline.mover_cabezal()
        if not ligero:
            partes += ["monitor", "inspector"]
        if partes:
            self.refrescar(*partes)

    def ir_a_minuto(self, minuto: int) -> None:
        self.mover_cabezal_a(max(0, min(MINUTOS_POR_CAPITULO - 1, minuto)) * FOTOGRAMAS_POR_MINUTO)

    def cambiar_capitulo(self, numero: int) -> None:
        self.monitor.detener()
        try:
            self.sesion.cambiar_capitulo(numero)
            self.sesion.capitulo  # carga perezosa: si falla, se avisa aquí
        except Exception as error:  # noqa: BLE001
            self.avisar(f"No se pudo abrir el capítulo {numero}: {error}")
            return
        self._minuto_visto = self.sesion.estado.minuto
        self.refrescar(*TODAS)

    def elegir_herramienta(self, nombre: str) -> None:
        self.sesion.estado.herramienta = nombre
        self.refrescar("timeline")

    def cambiar_zoom_timeline(self, paso: int = 0, nombre: str | None = None) -> None:
        estado = self.sesion.estado
        if nombre is None:
            indice = ZOOMS.index(estado.zoom_timeline) + paso
            nombre = ZOOMS[max(0, min(len(ZOOMS) - 1, indice))]
        if nombre in ("segundos", "fotograma"):
            visibles = ctl_timeline.FOTOGRAMAS_VISIBLES[nombre]
            estado.desplazamiento_timeline = max(0, min(FOTOGRAMAS_POR_CAPITULO - visibles, estado.cabezal - visibles // 2))
        estado.zoom_timeline = nombre
        self.refrescar("timeline")

    def abrir_bruto(self, id_bruto: str) -> None:
        if self.distribucion.activo != "taller":
            self.cambiar_espacio("taller")
        self.taller.abrir_bruto(id_bruto)
        self.refrescar("taller")

    def abrir_pieza(self, id_pieza: str) -> None:
        if self.distribucion.activo != "taller":
            self.cambiar_espacio("taller")
        self.taller.abrir_pieza(id_pieza)
        self.refrescar("taller")

    # --- Avisos y diálogos -------------------------------------------------------------

    def avisar(self, texto_aviso: str) -> None:
        """Regla del modelo violada o error: aviso breve que no cambia nada (22.6)."""
        self.raiz.avisar(texto_aviso)

    def aviso_breve(self, texto_aviso: str) -> None:
        self.barra_tareas.mensaje.value = texto_aviso
        self.refrescar("tareas")

    def confirmar(self, titulo: str, texto_dialogo: str, al_aceptar: Callable[[], None], aceptar: str = "Aceptar") -> None:
        self.raiz.dialogo(titulo, texto_dialogo, [(aceptar, al_aceptar), ("Cancelar", None)])

    # --- Edición -----------------------------------------------------------------------

    def deshacer(self) -> None:
        self.monitor.detener()
        self.sesion.deshacer()
        self.refrescar(*TODAS)

    def rehacer(self) -> None:
        self.monitor.detener()
        self.sesion.rehacer()
        self.refrescar(*TODAS)

    def guardar(self, forzar: bool = False, despues: Callable[[], None] | None = None) -> None:
        if self.sesion.solo_lectura:
            self.avisar("El proyecto está abierto en solo lectura: no se puede guardar.")
            return
        try:
            resultado = ctl_proyecto.guardar(self.sesion, forzar=forzar)
        except Exception as error:  # noqa: BLE001 — el diario permite reintentar
            self.avisar(f"No se pudo guardar: {error}")
            return
        if resultado.conflictos:
            lista = "\n".join(f"• {c.ruta}: {c.motivo}" for c in resultado.conflictos[:10])
            resto = len(resultado.conflictos) - 10
            if resto > 0:
                lista += f"\n… y {resto} más"
            self.raiz.dialogo(
                "Conflictos con el disco",
                "Estos archivos cambiaron fuera del programa desde la última lectura:\n\n" + lista,
                [
                    ("Conservar la versión del programa", lambda: self.guardar(forzar=True, despues=despues)),
                    ("Recargar desde el disco", self._recargar),
                    ("Cancelar", None),
                ],
            )
            return
        if resultado.errores:
            self.avisar("Guardado con errores:\n" + "\n".join(resultado.errores[:5]))
        else:
            self.aviso_breve(f"Guardado ({resultado.operaciones} operaciones).")
        self.refrescar("barra", "mapa")
        if despues is not None:
            despues()

    def _recargar(self) -> None:
        ruta = self.sesion.proyecto.raiz
        self.raiz.cerrar_proyecto()
        self.raiz.abrir(ruta)

    def pedir_cierre(self, al_cerrar: Callable[[], None] | None = None) -> None:
        """Cerrar el proyecto: con cambios, guardar / descartar / cancelar."""
        terminar = al_cerrar or (lambda: None)   # cerrar_proyecto ya vuelve al inicio

        def cerrar() -> None:
            self.raiz.cerrar_proyecto()
            terminar()

        if not self.sesion.historial.hay_cambios or self.sesion.solo_lectura:
            cerrar()
            return
        self.raiz.dialogo(
            "Cambios sin guardar",
            "El proyecto tiene cambios sin guardar.",
            [("Guardar", lambda: self.guardar(despues=cerrar)), ("Descartar", cerrar), ("Cancelar", None)],
        )

    # --- Bucles de fondo del hilo de Flet ----------------------------------------------

    async def _bucle_autosave(self) -> None:
        while self._abierta:
            await asyncio.sleep(INTERVALO_AUTOSAVE)
            if not self._abierta:
                break
            try:
                if self.sesion.guardado.autoguardar_si_hace_falta():
                    self.aviso_breve("Instantánea de autosave guardada.")
            except Exception as error:  # noqa: BLE001
                self.aviso_breve(f"Autosave falló: {error}")

    async def _bucle_prerender(self) -> None:
        """Tras unos segundos sin editar, prepara la vista previa fluida del minuto actual."""
        import time

        preparado: tuple | None = None
        while self._abierta:
            await asyncio.sleep(1.0)
            estado = self.sesion.estado
            if estado.reproduciendo or time.monotonic() - self._ultima_edicion < ESPERA_PRERENDER:
                continue
            clave = (estado.capitulo, estado.minuto, estado.idioma_escucha, self._ultima_edicion)
            if clave == preparado:
                continue
            preparado = clave
            if reproduccion.prerender_listo(self.sesion, estado.minuto) is None:
                reproduccion.preparar_minuto(self.sesion, estado.minuto, lambda _r: self.refrescar("mapa"))

    # --- Teclado -----------------------------------------------------------------------

    def _tecla_abajo(self, evento) -> None:
        self._teclas.add(evento.key)

    def _tecla_arriba(self, evento) -> None:
        self._teclas.discard(evento.key)

    def _teclado(self, evento: ft.KeyboardEvent) -> None:
        if self.raiz.hay_dialogo:
            return
        self.teclado.procesar(evento.key, evento.ctrl, evento.shift, evento.alt, evento.meta)

    def _registrar_atajos(self) -> None:
        t = self.teclado.registrar
        s = self.sesion
        en_taller = lambda: s.estado.foco == "taller"  # noqa: E731

        t("reproducir_pausar", self.monitor.alternar_reproduccion)
        t("reproducir", self.monitor.alternar_reproduccion)
        t("fotograma_anterior", lambda: self.taller.mover(-1) if en_taller() else self.mover_cabezal(-1))
        t("fotograma_siguiente", lambda: self.taller.mover(1) if en_taller() else self.mover_cabezal(1))
        t("segundo_anterior", lambda: self.taller.mover(-FPS) if en_taller() else self.mover_cabezal(-FPS))
        t("segundo_siguiente", lambda: self.taller.mover(FPS) if en_taller() else self.mover_cabezal(FPS))
        t("retroceder_segundo", lambda: self.mover_cabezal(-FPS))
        t("inicio_minuto", lambda: self.ir_a_minuto(s.estado.minuto))
        t("marcar_entrada", lambda: self.taller.marcar_entrada() if en_taller() else self._marca("entrada"))
        t("marcar_salida", lambda: self.taller.marcar_salida() if en_taller() else self._marca("salida"))
        t("dividir", self._dividir)
        t("marcador", lambda: ctl_timeline.poner_marcador(s) and self.refrescar("timeline"))
        t("deseleccionar", lambda: self.seleccionar(set()))
        for herramienta in ("seleccion", "cuchilla", "ripple", "roll", "slip", "slide"):
            t(f"herramienta_{herramienta}", lambda h=herramienta: self.elegir_herramienta(h))
        t("agregar_keyframe", self.inspector.agregar_keyframe)
        t("deshacer", self.deshacer)
        t("rehacer", self.rehacer)
        t("rehacer_alternativo", self.rehacer)
        t("guardar", self.guardar)
        t("copiar", lambda: self.aviso_breve(f"{ctl_timeline.copiar(s)} Elemento(s) copiados."))
        t("pegar", lambda: ctl_timeline.pegar(s) and self.refrescar("timeline", "monitor", "mapa"))
        t("duplicar", lambda: ctl_timeline.duplicar(s) and self.refrescar("timeline", "monitor", "mapa"))
        t("borrar", lambda: ctl_timeline.quitar_seleccion(s) and self.refrescar("timeline", "monitor", "inspector", "mapa"))
        t("ripple_borrar", lambda: ctl_timeline.quitar_seleccion(s, ripple=True)
          and self.refrescar("timeline", "monitor", "inspector", "mapa"))
        t("mover_1px", lambda direccion: self.monitor.mover_seleccion(direccion, 1))
        t("mover_10px", lambda direccion: self.monitor.mover_seleccion(direccion, 10))
        t("zoom_timeline_mas", lambda: self.cambiar_zoom_timeline(1))
        t("zoom_timeline_menos", lambda: self.cambiar_zoom_timeline(-1))
        t("minuto_anterior", lambda: self.ir_a_minuto(s.estado.minuto - 1))
        t("minuto_siguiente", lambda: self.ir_a_minuto(s.estado.minuto + 1))

    def _marca(self, cual: str) -> None:
        setattr(self.sesion.estado, cual, self.sesion.estado.cabezal)
        self.refrescar("timeline")

    def _dividir(self) -> None:
        """S: corta en el cabezal lo seleccionado (o todo lo que cruza el cabezal)."""
        s = self.sesion
        ids = sorted(s.estado.seleccion)
        hecho = ctl_timeline.cortar_en(s, s.estado.cabezal, ids[0]) if len(ids) == 1 else ctl_timeline.cortar_en(s, s.estado.cabezal)
        if hecho:
            self.refrescar("timeline", "monitor", "mapa")
