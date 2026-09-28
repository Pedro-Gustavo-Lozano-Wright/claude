"""Acciones creativas (E19): presets de animación, estabilizar, plantillas de texto y subtítulos."""

from __future__ import annotations

from pathlib import Path

from editor.app.estado import Sesion
from editor.core.comandos import AgregarElemento, CambiarEstadoCapa
from editor.core.comandos.compuesto import ComandoCompuesto
from editor.core.comandos.fabrica import elemento_texto
from editor.core.comandos import presets
from editor.core.estandar import FPS
from editor.core.modelo.capa import Capa
from editor.core.modelo.errores import ErrorModelo
from editor.core.modelo.marcador import clave_capa
from editor.core.servicios import analisis, subtitulos
from editor.core.tareas.cola import BANCO_VISIBLE, Tarea

MAXIMO_ESTABILIZAR = 60 * FPS


def _elemento(sesion: Sesion, id_elemento: str):
    elemento = sesion.capitulo.buscar(id_elemento)
    if elemento is None:
        raise ErrorModelo("El Elemento ya no existe.")
    return elemento


def ken_burns(sesion: Sesion, id_elemento: str, zoom: float = 1.15) -> bool:
    return sesion.ejecutar(lambda: presets.ken_burns(sesion.estado.capitulo, _elemento(sesion, id_elemento), zoom))


def animar_clip(sesion: Sesion, id_elemento: str, tipo: str, entrada: bool, duracion: int = 12) -> bool:
    return sesion.ejecutar(lambda: presets.animacion_clip(
        sesion.estado.capitulo, _elemento(sesion, id_elemento), tipo, entrada, duracion))


def estabilizar(sesion: Sesion, id_elemento: str) -> None:
    """Mide el movimiento del tramo de fuente que usa el Elemento (tarea) y lo corrige con keyframes."""
    elemento = sesion.capitulo.buscar(id_elemento)
    if elemento is None or not elemento.es_visual or elemento.es_texto:
        sesion.avisar("Elija un Elemento de video.")
        return
    if elemento.duracion > MAXIMO_ESTABILIZAR or elemento.con_rampa or elemento.tiempo.velocidad != 1:
        sesion.avisar("Se estabilizan clips de hasta 60 s a velocidad normal.")
        return
    ruta = sesion.vista_previa.resolutor(elemento)
    if ruta is None:
        sesion.avisar("No se encuentra el archivo del Elemento.")
        return
    desde = elemento.fotograma_fuente(elemento.inicio)
    hasta = desde + elemento.duracion
    capitulo = sesion.estado.capitulo

    def terminar(correcciones, error) -> None:
        if error is not None:
            sesion.avisar(f"No se pudo estabilizar: {error}")
            return
        actual = sesion.capitulo.buscar(id_elemento)
        if actual is None:
            return
        if sesion.ejecutar(lambda: presets.estabilizar(capitulo, actual, correcciones)):
            sesion.avisar(f"{actual.nombre} estabilizado ({len(correcciones)} fotogramas).")

    sesion.tarea(Tarea("analisis", f"Estabilizar {elemento.nombre}",
                       lambda contexto: analisis.movimiento(ruta, desde, hasta, contexto),
                       prioridad=BANCO_VISIBLE, clave=f"estabilizar-{id_elemento}"), terminar)


def importar_srt(sesion: Sesion, ruta: Path, codigo_capa: str, idioma: str) -> int:
    """Crea un texto (plantilla Subtítulo) por línea del `.srt` en la capa T elegida, de ese idioma.

    Todo en un paso de deshacer. Devuelve cuántos subtítulos se crearon (0 si falló).
    """
    try:
        lineas = subtitulos.leer_srt(ruta)
    except OSError as error:
        sesion.avisar(f"No se pudo leer {ruta.name}: {error}")
        return 0
    if not lineas:
        sesion.avisar(f"{ruta.name} no tiene subtítulos.")
        return 0
    capa = Capa.desde_codigo(codigo_capa)
    capitulo = sesion.estado.capitulo
    limite = len(sesion.capitulo.minutos) * 60 * FPS
    comandos = []
    if idioma:
        comandos.append(CambiarEstadoCapa(capitulo, clave_capa(codigo_capa, False), idioma=idioma))
    for linea in lineas:
        if linea.inicio >= limite:
            break
        elemento = elemento_texto(sesion.proyecto, capa, linea.inicio, linea.texto,
                                  duracion=min(linea.fin, limite) - linea.inicio,
                                  nombre=" ".join(linea.texto.split()[:4]), plantilla="subtitulo")
        comandos.append(AgregarElemento(capitulo, elemento))
    if sesion.ejecutar(lambda: ComandoCompuesto(f"Subtítulos de {ruta.name}", comandos)):
        return len(comandos) - (1 if idioma else 0)
    return 0


def exportar_srt(sesion: Sesion, codigo_capa: str, ruta: Path) -> int:
    return subtitulos.escribir_srt(sesion.capitulo, codigo_capa, ruta)
