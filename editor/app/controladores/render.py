"""Renderizar entregables desde la interfaz."""

from __future__ import annotations

from editor.app.estado import Sesion
from editor.core.estandar import FOTOGRAMAS_POR_MINUTO
from editor.core.servicios import capitulos_youtube, huellas, mantenimiento, render
from editor.core.servicios.importacion import EspacioInsuficiente
from editor.core.tareas.cola import RENDER_FINAL, Tarea
from editor.core.modelo.minuto import EstadoRender


def renderizar(sesion: Sesion, desde: int | None, hasta: int | None, perfil: str = render.VIDEO,
               normalizar: bool = True) -> None:
    """Un archivo con una pista de audio por idioma, más un `.srt` por idioma con subtítulos y
    los capítulos de YouTube. `normalizar`: cada pista a −14 LUFS sin pasar de −1 dBFS de pico."""
    if sesion.solo_lectura:
        sesion.avisar("El proyecto está abierto en solo lectura: no se puede renderizar.")
        return
    estandar = sesion.proyecto.estandar
    minutos = 24 if desde is None else (hasta if hasta is not None else desde) - desde + 1
    # El capítulo completo necesita los minutos más el ensamblado (otra copia).
    fotogramas = minutos * FOTOGRAMAS_POR_MINUTO * (2 if desde is None else 1)
    try:
        assert sesion.proyecto.raiz is not None
        if perfil == render.VIDEO:
            mantenimiento.comprobar_espacio(sesion.proyecto.raiz, mantenimiento.estimar_video(
                fotogramas, estandar.lienzo_ancho, estandar.lienzo_alto), "renderizar")
    except EspacioInsuficiente as error:
        sesion.avisar(str(error))
        return
    pedido = render.PedidoRender.crear(
        sesion.proyecto, sesion.estado.capitulo, desde, hasta,
        perfil=perfil,
        normalizar_lufs=render.LUFS_YOUTUBE if normalizar else None,
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


def capitulos_de_youtube(sesion: Sesion, desde: int | None = None, hasta: int | None = None) -> tuple[str, list[str]]:
    """Texto de capítulos para la descripción del video (desde los marcadores) y sus avisos."""
    inicio = 0 if desde is None else desde * FOTOGRAMAS_POR_MINUTO
    fin = 24 * FOTOGRAMAS_POR_MINUTO if desde is None else ((hasta if hasta is not None else desde) + 1) * FOTOGRAMAS_POR_MINUTO
    return capitulos_youtube.capitulos(sesion.capitulo, inicio, fin)


def estados_de_render(sesion: Sesion) -> dict[int, EstadoRender]:
    """Estado de render de los 24 minutos (para el mapa); ~20 ms con capítulos grandes."""
    capitulo = sesion.capitulo
    return {
        m.numero: huellas.estado_render(capitulo, m.numero, sesion.proyecto.estandar, sesion.vista_previa.resolutor)
        for m in capitulo.minutos
    }
