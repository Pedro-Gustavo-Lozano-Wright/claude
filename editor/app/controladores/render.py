"""Renderizar entregables desde la interfaz (E10; exportación completa en E21)."""

from __future__ import annotations

from editor.app.estado import Sesion
from editor.core.estandar import FOTOGRAMAS_POR_MINUTO
from editor.core.servicios import huellas, mantenimiento, render
from editor.core.servicios.importacion import EspacioInsuficiente
from editor.core.tareas.cola import RENDER_FINAL, Tarea
from editor.core.modelo.minuto import EstadoRender


LUFS_YOUTUBE = -14.0


def renderizar(sesion: Sesion, desde: int | None, hasta: int | None, por_idioma: bool = False,
               normalizar: bool = False) -> None:
    """`normalizar`: cada pista de idioma a −14 LUFS (YouTube) sin pasar de −1 dBFS de pico."""
    if sesion.solo_lectura:
        sesion.avisar("El proyecto está abierto en solo lectura: no se puede renderizar.")
        return
    estandar = sesion.proyecto.estandar
    minutos = 24 if desde is None else (hasta if hasta is not None else desde) - desde + 1
    # El capítulo completo necesita los minutos más el ensamblado (otra copia).
    fotogramas = minutos * FOTOGRAMAS_POR_MINUTO * (2 if desde is None else 1)
    try:
        assert sesion.proyecto.raiz is not None
        mantenimiento.comprobar_espacio(sesion.proyecto.raiz, mantenimiento.estimar_video(
            fotogramas, estandar.lienzo_ancho, estandar.lienzo_alto), "renderizar")
    except EspacioInsuficiente as error:
        sesion.avisar(str(error))
        return
    pedido = render.PedidoRender.crear(
        sesion.proyecto, sesion.estado.capitulo, desde, hasta,
        modo=render.ARCHIVOS if por_idioma else render.PISTAS,
        normalizar_lufs=LUFS_YOUTUBE if normalizar else None,
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
