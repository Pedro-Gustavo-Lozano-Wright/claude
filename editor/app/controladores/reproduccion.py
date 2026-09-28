"""Imágenes del monitor, reproducción y pre-render (E13, PROJECT.md 12 y 22.9).

- Cada pedido de imagen es una tarea de prioridad 1 con `clave="monitor"`: si
  llega otro antes de que termine, el viejo se cancela (el cabezal manda).
- Nivel 1–2 (rápido, banco) primero; en pausa, después el nivel 4 (exacto).
- Las tareas trabajan sobre una **instantánea parcial** del capítulo: solo lo
  que toca ese fotograma (copiar el capítulo entero es lento).
"""

from __future__ import annotations

from typing import Callable

from editor.app.estado import Sesion
from editor.core.estandar import FOTOGRAMAS_POR_MINUTO, LIENZO_ALTO, LIENZO_ANCHO
from editor.core.tareas.cola import MONITOR, PRERENDER_ACTUAL, PRERENDER_RESTO, Tarea
from editor.core.tiempo import granularidad

TAMANO_RAPIDO = (640, 360)


def tamano_exacto(ancho_monitor: float) -> tuple[int, int]:
    ancho = int(max(320, min(LIENZO_ANCHO, ancho_monitor)))
    return ancho, round(ancho * LIENZO_ALTO / LIENZO_ANCHO)


def pedir_imagen(sesion: Sesion, al_llegar: Callable[[bytes, int], None], exacta: bool = False,
                 ancho_monitor: float = 960) -> None:
    f = sesion.estado.cabezal
    capitulo = sesion.capitulo.instantanea(f, f + 1)
    servicio = sesion.vista_previa
    tamano = tamano_exacto(ancho_monitor) if exacta else TAMANO_RAPIDO

    def trabajo(contexto):
        contexto.comprobar()
        if exacta:
            return servicio.fotograma_exacto(capitulo, f, tamano)
        return servicio.fotograma_rapido(capitulo, f, tamano)

    def terminar(resultado, error) -> None:
        if error is None and resultado is not None:
            al_llegar(resultado, f)

    sesion.tarea(Tarea("monitor", "Monitor", trabajo, prioridad=MONITOR, clave="monitor"), terminar)


def instantanea_en(sesion: Sesion, f: int):
    """Copia mínima del capítulo para componer el fotograma f fuera del hilo principal."""
    return sesion.capitulo.instantanea(f, f + 1)


def fotograma_en_vivo(sesion: Sesion, capitulo, f: int) -> bytes:
    """Nivel 2 durante la reproducción. Corre en un hilo aparte (`asyncio.to_thread`);
    `capitulo` es la instantánea tomada antes en el hilo principal."""
    return sesion.vista_previa.fotograma_rapido(capitulo, f, TAMANO_RAPIDO)


def preparar_minuto(sesion: Sesion, minuto: int, al_terminar: Callable[[object], None] | None = None,
                    actual: bool = True) -> None:
    """Pre-render (nivel 3) de un minuto en segundo plano."""
    inicio, fin = granularidad.rango_minuto(minuto)
    capitulo = sesion.capitulo.instantanea(inicio, fin)
    idioma = sesion.estado.idioma_escucha
    servicio = sesion.vista_previa

    def terminar(resultado, error) -> None:
        if error is None and al_terminar is not None:
            al_terminar(resultado)

    sesion.tarea(
        Tarea("prerender", f"Vista previa del minuto {minuto:02d}",
              lambda contexto: servicio.prerender_minuto(capitulo, minuto, idioma, contexto),
              prioridad=PRERENDER_ACTUAL if actual else PRERENDER_RESTO, clave=f"prerender-{minuto}"),
        terminar,
    )


def audio_del_minuto(sesion: Sesion, minuto: int, al_terminar: Callable[[object], None]) -> None:
    inicio, fin = granularidad.rango_minuto(minuto)
    capitulo = sesion.capitulo.instantanea(inicio, fin)
    idioma = sesion.estado.idioma_escucha
    servicio = sesion.vista_previa
    sesion.tarea(
        Tarea("audio", f"Audio del minuto {minuto:02d}",
              lambda contexto: servicio.audio(capitulo, inicio, fin, idioma, contexto),
              prioridad=PRERENDER_ACTUAL, clave=f"audio-{minuto}"),
        lambda resultado, error: al_terminar(resultado) if error is None else None,
    )


def prerender_listo(sesion: Sesion, minuto: int):
    """Ruta del pre-render vigente del minuto, o None si hay que generarlo."""
    inicio, fin = granularidad.rango_minuto(minuto)
    ruta = sesion.vista_previa.ruta_prerender(sesion.capitulo.instantanea(inicio, fin), minuto, sesion.estado.idioma_escucha)
    return ruta if ruta.exists() else None


def minuto_de(f: int) -> int:
    return min(23, f // FOTOGRAMAS_POR_MINUTO)
