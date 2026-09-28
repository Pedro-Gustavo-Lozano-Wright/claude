"""Importar archivos como Brutos.

preparar (principal) → copiar y analizar (tarea) → `AgregarBruto` + `BrutoImportado` (principal).
"""

from __future__ import annotations

from pathlib import Path

from editor.app.estado import Sesion
from editor.core.comandos.taller import AgregarBruto
from editor.core.eventos import BrutoImportado
from editor.core.servicios import importacion
from editor.core.tareas.cola import BANCO_VISIBLE, Tarea


def importar(sesion: Sesion, rutas: list[Path]) -> None:
    proyecto = sesion.proyecto
    assert proyecto.raiz is not None
    if sesion.solo_lectura:
        sesion.avisar("El proyecto está abierto en solo lectura: no se puede importar.")
        return
    raiz = proyecto.raiz
    for origen in rutas:
        if not origen.is_file():
            sesion.avisar(f"No es un archivo: {origen}")
            continue
        bruto = importacion.preparar_bruto(proyecto, origen)
        # El número se reserva al preparar; si se importan varios a la vez, se evita repetirlo.
        ocupados = {b.numero for b in proyecto.taller.brutos.values()}
        while bruto.numero in ocupados or bruto.numero in _reservados:
            bruto.numero += 1
        _reservados.add(bruto.numero)

        def terminar(resultado, error, numero=bruto.numero, nombre=origen.name) -> None:
            _reservados.discard(numero)
            if error is not None:
                sesion.avisar(f"No se pudo importar {nombre}: {error}")
                return
            if sesion.ejecutar(AgregarBruto(resultado)):
                sesion.vista_previa.actualizar_taller(proyecto)
                sesion.bus.publicar(BrutoImportado(resultado.id))
                if resultado.necesita_revision_fps:
                    sesion.avisar(f"{nombre}: revise el fps (declarado {resultado.fps_detectado}, "
                                  f"medido {resultado.fps_medido}{', variable' if resultado.vfr else ''}).")

        sesion.tarea(
            Tarea("importar", f"Importar {origen.name}",
                  lambda contexto, b=bruto, o=origen: importacion.copiar_y_analizar(raiz, b, o, contexto),
                  prioridad=BANCO_VISIBLE),
            terminar,
        )


_reservados: set[int] = set()
