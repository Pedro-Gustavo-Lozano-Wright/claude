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
from editor.core.comandos.compuesto import ComandoCompuesto
from editor.core.comandos.proyecto import CambiarIdiomas
from editor.core.comandos.taller import QuitarBruto
from editor.core.estandar import Estandar
from editor.core.servicios import mantenimiento
from editor.core.eventos import BusEventos, CapituloCreado, ProyectoAbierto
from editor.core.proyecto_fs import autosave, consultas, estructura
from editor.core.proyecto_fs.bloqueo import InfoBloqueo, ProyectoBloqueado
from editor.core.proyecto_fs.escaner import Informe, NoEsProyecto, abrir_proyecto
from editor.core.proyecto_fs.reconciliador import ResultadoGuardado, registrar_manifiesto_proyecto


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
    if not solo_lectura:
        mantenimiento.limpiar_parciales(apertura.proyecto.raiz)
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
    # Lo restaurado no está en disco: hasta guardar, cerrar o cambiar de capítulo pregunta.
    sesion.historial.marcar_sin_guardar()


def descartar_autosave(sesion: Sesion) -> None:
    assert sesion.proyecto.raiz is not None
    autosave.descartar_instantanea(sesion.proyecto.raiz)


def guardar(sesion: Sesion, forzar: bool = False) -> ResultadoGuardado:
    return sesion.guardado.guardar(forzar=forzar)


# --- Idiomas del proyecto (E18) ---------------------------------------------------------

def cambiar_idiomas(sesion: Sesion, idiomas: list[str]) -> bool:
    """El primero es el principal. Se deshace; las capas A que usen un idioma quitado lo impiden."""
    assert sesion.proyecto.raiz is not None
    cargados = {c.numero for c in sesion.proyecto.capitulos_cargados()}
    fuera = consultas.idiomas_en_disco(sesion.proyecto.raiz, cargados)
    if sesion.ejecutar(lambda: CambiarIdiomas(idiomas, fuera)):
        if sesion.estado.idioma_escucha not in sesion.proyecto.idiomas:
            sesion.estado.idioma_escucha = sesion.proyecto.idioma_principal or None
        return True
    return False


# --- Mantenimiento (E18) ----------------------------------------------------------------

def tamanos(sesion: Sesion) -> dict[str, int]:
    assert sesion.proyecto.raiz is not None
    return mantenimiento.tamanos(sesion.proyecto.raiz)


def vaciar_cache(sesion: Sesion) -> int:
    """Con la cola en marcha podría borrarse algo que una tarea está escribiendo: se exige que esté quieta."""
    if sesion.cola.pendientes():
        raise RuntimeError("Hay tareas en cola; espere a que terminen.")
    sesion.vista_previa.olvidar()
    assert sesion.proyecto.raiz is not None
    return mantenimiento.vaciar_cache(sesion.proyecto.raiz)


def vaciar_papelera(sesion: Sesion) -> int:
    """Deshacer después de guardar recupera archivos de la papelera: se guarda antes y se olvida el historial."""
    if sesion.solo_lectura:
        raise RuntimeError("El proyecto está abierto en solo lectura.")
    if sesion.historial.hay_cambios:
        raise RuntimeError("Guarde antes de vaciar la papelera.")
    assert sesion.proyecto.raiz is not None
    liberados = mantenimiento.vaciar_papelera(sesion.proyecto.raiz)
    sesion.historial.vaciar()
    return liberados


def brutos_sin_uso(sesion: Sesion) -> list[str]:
    return mantenimiento.brutos_sin_uso(sesion.proyecto)


def quitar_brutos(sesion: Sesion, ids: list[str]) -> bool:
    if not ids:
        return False
    return sesion.ejecutar(lambda: ComandoCompuesto("Quitar Brutos sin uso", [QuitarBruto(i) for i in ids]))


def nuevo_capitulo(sesion: Sesion, titulo: str = "") -> int:
    """Crea el siguiente capítulo (en disco en el momento; no se deshace)."""
    capitulo = estructura.crear_capitulo(sesion.proyecto, titulo=titulo)
    registrar_manifiesto_proyecto(sesion.proyecto, sesion.apertura.estado)
    sesion.bus.publicar(CapituloCreado(capitulo.numero))
    return capitulo.numero


def recientes(ajustes: Ajustes) -> list[Path]:
    return [Path(r) for r in ajustes.proyectos_recientes if Path(r).exists()]


def resumen_informe(informe: Informe | None) -> str:
    if informe is None or informe.avisos == 0:
        return ""
    return informe.resumen()
