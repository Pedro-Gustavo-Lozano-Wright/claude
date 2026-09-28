"""Renderizar entregables desde la interfaz (E10; exportación completa en E21)."""

from __future__ import annotations

from editor.app.estado import Sesion
from editor.core.servicios import huellas, render
from editor.core.tareas.cola import RENDER_FINAL, Tarea
from editor.core.modelo.minuto import EstadoRender


def renderizar(sesion: Sesion, desde: int | None, hasta: int | None, por_idioma: bool = False) -> None:
    if sesion.solo_lectura:
        sesion.avisar("El proyecto está abierto en solo lectura: no se puede renderizar.")
        return
    pedido = render.PedidoRender.crear(
        sesion.proyecto, sesion.estado.capitulo, desde, hasta,
        modo=render.ARCHIVOS if por_idioma else render.PISTAS,
    )
    descripcion = "capítulo completo" if desde is None else (
        f"minuto {desde:02d}" if hasta in (None, desde) else f"minutos {desde:02d}-{hasta:02d}")

    def terminar(resultado, error) -> None:
        if error is not None:
            sesion.avisar(f"Falló el render ({descripcion}): {error}")
            return
        render.registrar(sesion.proyecto, sesion.apertura.estado, resultado, sesion.bus)
        sesion.avisar("Render listo: " + ", ".join(a.name for a in resultado.archivos))

    sesion.tarea(Tarea("render", f"Render {descripcion}", lambda contexto: render.renderizar(pedido, contexto),
                       prioridad=RENDER_FINAL), terminar)


def estados_de_render(sesion: Sesion) -> dict[int, EstadoRender]:
    """Estado de render de los 24 minutos (para el mapa); ~20 ms con capítulos grandes."""
    capitulo = sesion.capitulo
    return {
        m.numero: huellas.estado_render(capitulo, m.numero, sesion.proyecto.estandar, sesion.vista_previa.resolutor)
        for m in capitulo.minutos
    }
