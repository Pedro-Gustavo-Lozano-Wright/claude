"""Estado de la aplicación y sesión de trabajo (E12, PROJECT.md 22.1).

- `EstadoApp`: cómo mira el usuario el proyecto (capítulo, cabezal, selección,
  herramienta, zoom…). No se deshace, no se guarda en el proyecto.
- `Sesion`: reúne todo lo que vive mientras un proyecto está abierto: modelo,
  historial, bus, cola de tareas, vista previa y guardado. Es el único punto
  por el que la interfaz toca el núcleo.

Hilos (PROJECT.md 22.4 y 22.8): la interfaz y el modelo viven en el bucle de
Flet. Todo lo que llega desde una tarea de fondo entra por `en_principal`,
que usa `page.run_task` (seguro entre hilos).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from editor.core.ajustes import Ajustes
from editor.core.comandos.comando import Comando
from editor.core.comandos.historial import Historial
from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO, FOTOGRAMAS_POR_MINUTO
from editor.core.eventos import BusEventos, Evento
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.errores import ErrorModelo
from editor.core.proyecto_fs.escaner import Apertura
from editor.core.servicios.guardado import ServicioGuardado
from editor.core.servicios.vista_previa import ServicioVistaPrevia
from editor.core.tareas.cola import ColaTareas, Tarea
from editor.core.tiempo import granularidad

registro = logging.getLogger(__name__)

HERRAMIENTAS = ("seleccion", "cuchilla", "ripple", "roll", "slip", "slide")
ZOOMS = ("capitulo", "minuto", "segundos", "fotograma")
ESPACIOS = ("taller", "minuto", "capitulo", "shorts", "render")


@dataclass
class EstadoApp:
    capitulo: int = 1
    cabezal: int = 0
    seleccion: set[str] = field(default_factory=set)
    herramienta: str = "seleccion"
    zoom_timeline: str = "minuto"
    desplazamiento_timeline: int = 0      # primer fotograma visible (zooms menores que un minuto)
    zoom_lienzo: float = 0.0              # 0 = encajar
    espacio_trabajo: str = "minuto"
    reproduciendo: bool = False
    idioma_escucha: str | None = None
    foco: str = "timeline"                # monitor, timeline, taller, texto
    portapapeles: list[Elemento] = field(default_factory=list)
    iman: bool = True
    seguir_cabezal: bool = True
    capa_destino: str = "V1"              # capa donde se colocan Piezas nuevas
    destino_global: bool = False          # colocar en Global (abarca minutos: música, logo fijo)
    capa_destino_audio: str = "A1"        # capa donde se colocan los audios
    entrada: int | None = None            # marcas I / O de la timeline (fotogramas del capítulo)
    salida: int | None = None

    @property
    def minuto(self) -> int:
        return min(granularidad.minuto_de(self.cabezal), 23)


class Sesion:
    """Un proyecto abierto con todos sus servicios."""

    def __init__(
        self,
        apertura: Apertura,
        ajustes: Ajustes,
        bus: BusEventos,
        en_principal: Callable[[Callable[[], None]], None],
    ) -> None:
        self.apertura = apertura
        self.ajustes = ajustes
        self.bus = bus
        self.en_principal = en_principal
        self.proyecto = apertura.proyecto
        self.estado = EstadoApp(idioma_escucha=self.proyecto.idioma_principal or None)
        self.historial = Historial(self.proyecto, bus, ajustes.historial_pasos)
        self.cola = ColaTareas(bus, ajustes.trabajadores_fondo)
        self.vista_previa = ServicioVistaPrevia(
            self.proyecto, ajustes.vista_previa_calidad_jpeg, ajustes.monitor_calidad_pausa_jpeg,
            ajustes.cache_fotogramas_mb,
        )
        self.guardado = ServicioGuardado(
            apertura, self.historial, bus, self.cola, en_principal,
            al_cerrar_archivos=self.vista_previa.olvidar, autosave_segundos=ajustes.autosave_segundos,
        )
        self.avisar: Callable[[str], None] = lambda texto: registro.info("%s", texto)
        numeros = self.proyecto.numeros_capitulos()
        if numeros:
            self.estado.capitulo = numeros[0]

    # --- Acceso -------------------------------------------------------------------------

    @property
    def solo_lectura(self) -> bool:
        return self.apertura.solo_lectura

    @property
    def capitulo(self) -> Capitulo:
        return self.proyecto.capitulo(self.estado.capitulo)

    def seleccionados(self) -> list[Elemento]:
        capitulo = self.capitulo
        return [e for e in (capitulo.buscar(i) for i in sorted(self.estado.seleccion)) if e is not None]

    def seleccionado(self) -> Elemento | None:
        elementos = self.seleccionados()
        return elementos[0] if len(elementos) == 1 else None

    # --- Edición ------------------------------------------------------------------------

    def ejecutar(self, comando: Comando | Callable[[], Comando]) -> bool:
        """Ejecuta un comando; si el modelo lo rechaza, avisa y devuelve False.

        Acepta también una función que construye el comando: los constructores
        validan sus argumentos con `ValueError`, que así también se avisa.
        """
        if self.solo_lectura:
            self.avisar("El proyecto está abierto en solo lectura.")
            return False
        try:
            self.historial.ejecutar(comando if isinstance(comando, Comando) else comando())
            return True
        except (ErrorModelo, ValueError) as error:
            self.avisar(str(error))
            return False

    def deshacer(self) -> None:
        comando = self.historial.deshacer()
        if comando is not None:
            self.avisar(f"Deshecho: {comando.descripcion}")
        self._limpiar_seleccion()

    def rehacer(self) -> None:
        comando = self.historial.rehacer()
        if comando is not None:
            self.avisar(f"Rehecho: {comando.descripcion}")
        self._limpiar_seleccion()

    def _limpiar_seleccion(self) -> None:
        capitulo = self.capitulo
        self.estado.seleccion = {i for i in self.estado.seleccion if capitulo.buscar(i) is not None}

    # --- Navegación ---------------------------------------------------------------------

    def ir_a(self, f: int) -> None:
        self.estado.cabezal = max(0, min(FOTOGRAMAS_POR_CAPITULO - 1, f))

    def ir_a_minuto(self, minuto: int) -> None:
        self.ir_a(minuto * FOTOGRAMAS_POR_MINUTO + (self.estado.cabezal % FOTOGRAMAS_POR_MINUTO))

    def cambiar_capitulo(self, numero: int) -> bool:
        """Un solo capítulo en memoria (E18): cambiar es cerrar uno y abrir otro.

        Con cambios sin guardar no se cambia (la interfaz ofrece guardar antes). El
        historial empieza de nuevo: sus pasos eran del capítulo que se cierra.
        """
        if numero == self.estado.capitulo and numero in self.proyecto.capitulos:
            return True
        if self.historial.hay_cambios:
            self.avisar("Guarde antes de cambiar de capítulo.")
            return False
        anterior = self.estado.capitulo
        self.proyecto.capitulo(numero)          # carga; si falla, no se cambió nada
        self.estado.capitulo = numero
        self.estado.seleccion.clear()
        self.estado.cabezal = 0
        self.estado.entrada = self.estado.salida = None
        self.estado.portapapeles.clear()
        self.descargar_otros_capitulos()
        if anterior != numero:
            self.historial.vaciar()
        return True

    def descargar_otros_capitulos(self) -> list[int]:
        """Deja en memoria solo el capítulo actual."""
        otros = [c.numero for c in self.proyecto.capitulos_cargados() if c.numero != self.estado.capitulo]
        for numero in otros:
            self.proyecto.descargar_capitulo(numero)
        return otros

    # --- Tareas -------------------------------------------------------------------------

    def tarea(self, tarea: Tarea, al_terminar_principal: Callable[[Any, BaseException | None], None] | None = None,
              del_capitulo: bool = False) -> str:
        """Envía una tarea; su `al_terminar` se ejecuta en el hilo principal.

        `del_capitulo`: el resultado edita el capítulo actual (sincronizar, estabilizar, bajar la
        música…). Si al terminar el usuario ya cambió de capítulo, no se aplica: se avisa.
        """
        if al_terminar_principal is not None:
            numero = self.estado.capitulo

            def terminar(resultado, error) -> None:
                if del_capitulo and self.estado.capitulo != numero:
                    self.avisar(f"«{tarea.descripcion}» terminó después de cambiar de capítulo: no se aplicó.")
                    return
                al_terminar_principal(resultado, error)

            tarea.al_terminar = lambda resultado, error: self.en_principal(lambda: terminar(resultado, error))
        return self.cola.enviar(tarea)

    def escuchar(self, tipo: type[Evento], manejador: Callable[[Any], None]) -> Callable[[], None]:
        """Suscribe un manejador que siempre corre en el hilo principal (los eventos de tareas llegan de otros hilos)."""
        return self.bus.suscribir(tipo, lambda evento: self.en_principal(lambda: manejador(evento)))

    def cerrar(self) -> None:
        self.cola.detener(esperar=False)
        self.vista_previa.olvidar()
        self.apertura.cerrar()


def hacer_en_principal(page) -> Callable[[Callable[[], None]], None]:
    """Función que ejecuta en el bucle de Flet algo pedido desde cualquier hilo."""

    def en_principal(funcion: Callable[[], None]) -> None:
        async def envoltura() -> None:
            try:
                funcion()
            except Exception:  # noqa: BLE001
                registro.exception("Error en el hilo principal")

        sesion = getattr(page, "session", None)
        conexion = getattr(sesion, "connection", None)
        if conexion is None:
            # La ventana ya se cerró: lo que llegue tarde de una tarea se descarta.
            registro.debug("Sin conexión con la interfaz; se descarta una llamada al hilo principal.")
            return
        try:
            dentro_del_bucle = conexion.loop is asyncio.get_running_loop()
        except RuntimeError:
            dentro_del_bucle = False
        if dentro_del_bucle:
            funcion()
        else:
            page.run_task(envoltura)

    return en_principal
