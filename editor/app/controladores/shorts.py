"""Shorts verticales desde la interfaz."""

from __future__ import annotations

from editor.app.estado import Sesion
from editor.core.comandos.compuesto import ComandoCompuesto
from editor.core.comandos import CambiarRangoShort, CrearShort, MoverVentanaShort, PonerKeyframeVentana, QuitarShort
from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO
from editor.core.modelo.keyframe import Keyframe
from editor.core.modelo.short import Short, VentanaVertical
from editor.core.servicios import shorts
from editor.core.espacio.lienzo import LIENZO
from editor.core.tareas.cola import MONITOR, RENDER_FINAL, Tarea
from editor.core.tiempo.nomenclatura import normalizar_nombre


def crear(sesion: Sesion, nombre: str = "short") -> str | None:
    """Con entrada y salida marcadas usa ese rango; si no, 30 s desde el cabezal."""
    estado = sesion.estado
    if estado.entrada is not None and estado.salida is not None and estado.salida > estado.entrada:
        inicio, duracion = estado.entrada, estado.salida - estado.entrada
    else:
        inicio, duracion = estado.cabezal, shorts.DURACION_SUGERIDA
    duracion = min(duracion, shorts.DURACION_MAXIMA, FOTOGRAMAS_POR_CAPITULO - inicio)
    if duracion <= 0:
        sesion.avisar("No queda tiempo del capítulo después del cabezal.")
        return None
    short = Short(id=sesion.proyecto.nuevo_id(), nombre=normalizar_nombre(nombre), inicio=inicio,
                  duracion=duracion, ventana=VentanaVertical())
    return short.id if sesion.ejecutar(CrearShort(estado.capitulo, short)) else None


def quitar(sesion: Sesion, id_short: str) -> bool:
    return sesion.ejecutar(QuitarShort(sesion.estado.capitulo, id_short))


def renombrar(sesion: Sesion, id_short: str, nombre: str) -> bool:
    short = sesion.capitulo.shorts.get(id_short)
    if short is None:
        return False
    return sesion.ejecutar(CambiarRangoShort(sesion.estado.capitulo, id_short, short.inicio, short.duracion,
                                             normalizar_nombre(nombre)))


def usar_rango_io(sesion: Sesion, id_short: str) -> bool:
    estado = sesion.estado
    if estado.entrada is None or estado.salida is None or estado.salida <= estado.entrada:
        sesion.avisar("Marque entrada (I) y salida (O) en la timeline.")
        return False
    duracion = min(estado.salida - estado.entrada, shorts.DURACION_MAXIMA)
    return sesion.ejecutar(CambiarRangoShort(estado.capitulo, id_short, estado.entrada, duracion))


def mover_ventana(sesion: Sesion, id_short: str, x: float, zoom: float) -> bool:
    """Sin keyframes mueve la ventana fija; con keyframes pone uno en el cabezal."""
    short = sesion.capitulo.shorts.get(id_short)
    if short is None:
        return False
    if short.ventana.animacion.tiene("x") or short.ventana.animacion.tiene("zoom"):
        return poner_keyframe(sesion, id_short, x, zoom)
    return sesion.ejecutar(MoverVentanaShort(sesion.estado.capitulo, id_short, x, zoom))


def poner_keyframe(sesion: Sesion, id_short: str, x: float, zoom: float) -> bool:
    """Keyframe de posición y zoom en el cabezal: la ventana sigue la acción."""
    short = sesion.capitulo.shorts.get(id_short)
    if short is None:
        return False
    f = sesion.estado.cabezal - short.inicio
    if not 0 <= f < short.duracion:
        sesion.avisar("Lleve el cabezal dentro del Short para poner un keyframe.")
        return False
    numero = sesion.estado.capitulo
    return sesion.ejecutar(ComandoCompuesto("Keyframe de la ventana", [
        PonerKeyframeVentana(numero, id_short, "x", Keyframe(f, x)),
        PonerKeyframeVentana(numero, id_short, "zoom", Keyframe(f, zoom)),
    ]))


def quitar_keyframes(sesion: Sesion, id_short: str) -> bool:
    """Vuelve a una ventana fija en la posición actual del cabezal."""
    short = sesion.capitulo.shorts.get(id_short)
    if short is None:
        return False
    x, zoom = ventana_en_cabezal(sesion, id_short)
    numero = sesion.estado.capitulo
    comandos = [PonerKeyframeVentana(numero, id_short, propiedad, None, k.f)
                for propiedad in ("x", "zoom") if short.ventana.animacion.tiene(propiedad)
                for k in short.ventana.animacion.pista(propiedad).keyframes]
    return sesion.ejecutar(ComandoCompuesto("Ventana fija", comandos + [MoverVentanaShort(numero, id_short, x, zoom)]))


def ventana_en_cabezal(sesion: Sesion, id_short: str) -> tuple[float, float]:
    short = sesion.capitulo.shorts[id_short]
    f = min(max(0, sesion.estado.cabezal - short.inicio), short.duracion - 1)
    animacion = short.ventana.animacion
    return animacion.valor("x", f, short.ventana.x), max(1.0, animacion.valor("zoom", f, short.ventana.zoom))


TAMANO_VISTA = (270, 480)


def vista_vertical(sesion: Sesion, id_short: str, f: int, x: float, zoom: float, al_llegar) -> None:
    """Fotograma `f` del capítulo a través de una ventana (x, zoom) sin tocar el Short:
    sirve para ver el encuadre mientras se arrastra (tarea de prioridad del monitor)."""
    if id_short not in sesion.capitulo.shorts:
        return
    capitulo = sesion.capitulo.instantanea(f, f + 1)
    ventana = LIENZO.ventana_vertical(x, zoom)
    servicio, idioma = sesion.vista_previa, shorts.idioma_short(sesion.proyecto)
    sesion.tarea(Tarea("visor", "Vista del Short",
                       lambda contexto: servicio.fotograma_ventana(capitulo, f, TAMANO_VISTA, ventana, idioma),
                       prioridad=MONITOR, clave="short-visor"),
                 lambda resultado, error: al_llegar(resultado) if error is None and resultado else None)


def estado(sesion: Sesion, id_short: str) -> str:
    return shorts.estado(sesion.proyecto, sesion.capitulo, sesion.capitulo.shorts[id_short],
                         sesion.vista_previa.resolutor)


def renderizar(sesion: Sesion, ids: list[str] | None = None) -> int:
    """Renderiza los Shorts pedidos (por defecto, los que no están al día). Devuelve cuántos."""
    if sesion.solo_lectura:
        sesion.avisar("El proyecto está abierto en solo lectura: no se puede renderizar.")
        return 0
    numero = sesion.estado.capitulo
    ids = ids if ids is not None else shorts.desactualizados(sesion.proyecto, numero)
    for id_short in ids:
        pedido = shorts.PedidoShort.crear(sesion.proyecto, numero, id_short)

        def terminar(resultado, error, nombre=pedido.short.nombre) -> None:
            if error is not None:
                sesion.avisar(f"Falló el Short {nombre}: {error}")
                return
            shorts.registrar(sesion.proyecto, sesion.apertura.estado, resultado)
            sesion.avisar(f"Short listo: {resultado.archivo.name}")

        sesion.tarea(Tarea("render", f"Short {pedido.short.nombre}",
                           lambda contexto, p=pedido: shorts.renderizar(p, contexto), prioridad=RENDER_FINAL),
                     terminar)
    return len(ids)
