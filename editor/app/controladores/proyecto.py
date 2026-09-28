"""Abrir, crear, guardar y cerrar proyectos (E12).

Secuencia de apertura (PROJECT.md 22.5): bloqueo → diario pendiente →
`_proyecto.json` → Taller → cargador de capítulos → ¿autosave más reciente?
Los diálogos (solo lectura, restaurar) los decide la interfaz con lo que
devuelven estas funciones.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from editor.app.estado import Sesion
from editor.core.ajustes import Ajustes
from editor.core.estandar import Estandar
from editor.core.eventos import BusEventos, CapituloCreado, ProyectoAbierto
from editor.core.proyecto_fs import autosave, estructura
from editor.core.proyecto_fs.bloqueo import InfoBloqueo, ProyectoBloqueado
from editor.core.proyecto_fs.escaner import Informe, NoEsProyecto, abrir_proyecto
from editor.core.proyecto_fs.reconciliador import ResultadoGuardado


@dataclass
class ResultadoApertura:
    sesion: Sesion | None = None
    error: str = ""
    bloqueado_por: InfoBloqueo | None = None   # ofrecer abrir en solo lectura
    autosave_pendiente: bool = False            # ofrecer restaurar
    informe: Informe | None = None


def abrir(
    ruta: Path,
    ajustes: Ajustes,
    bus: BusEventos,
    en_principal: Callable[[Callable[[], None]], None],
    solo_lectura: bool = False,
) -> ResultadoApertura:
    try:
        apertura = abrir_proyecto(ruta, solo_lectura=solo_lectura)
    except NoEsProyecto as error:
        return ResultadoApertura(error=str(error))
    except ProyectoBloqueado as error:
        return ResultadoApertura(error=str(error), bloqueado_por=error.info)
    except Exception as error:  # noqa: BLE001 — la interfaz debe mostrarlo, no caerse
        return ResultadoApertura(error=f"No se pudo abrir el proyecto: {error}")
    sesion = Sesion(apertura, ajustes, bus, en_principal)
    ajustes.registrar_reciente(ruta)
    ajustes.guardar_usuario()
    assert apertura.proyecto.raiz is not None
    pendiente = autosave.instantanea_mas_reciente(apertura.proyecto.raiz) is not None and not solo_lectura
    bus.publicar(ProyectoAbierto(str(apertura.proyecto.raiz)))
    return ResultadoApertura(sesion=sesion, autosave_pendiente=pendiente, informe=apertura.informe)


def crear(
    ruta: Path,
    ajustes: Ajustes,
    bus: BusEventos,
    en_principal: Callable[[Callable[[], None]], None],
    estandar: Estandar | None = None,
) -> ResultadoApertura:
    try:
        proyecto = estructura.crear_proyecto(ruta, estandar=estandar)
        estructura.crear_capitulo(proyecto, 1)
    except (estructura.ProyectoExistente, OSError) as error:
        return ResultadoApertura(error=str(error))
    return abrir(ruta, ajustes, bus, en_principal)


def restaurar_autosave(sesion: Sesion) -> None:
    autosave.restaurar_instantanea(sesion.proyecto)
    sesion.vista_previa.actualizar_taller(sesion.proyecto)


def descartar_autosave(sesion: Sesion) -> None:
    assert sesion.proyecto.raiz is not None
    autosave.descartar_instantanea(sesion.proyecto.raiz)


def guardar(sesion: Sesion, forzar: bool = False) -> ResultadoGuardado:
    return sesion.guardado.guardar(forzar=forzar)


def nuevo_capitulo(sesion: Sesion, titulo: str = "") -> int:
    """Crea el siguiente capítulo (en disco en el momento; no se deshace)."""
    capitulo = estructura.crear_capitulo(sesion.proyecto, titulo=titulo)
    sesion.bus.publicar(CapituloCreado(capitulo.numero))
    return capitulo.numero


def recientes(ajustes: Ajustes) -> list[Path]:
    return [Path(r) for r in ajustes.proyectos_recientes if Path(r).exists()]


def resumen_informe(informe: Informe | None) -> str:
    if informe is None or informe.avisos == 0:
        return ""
    return informe.resumen()
