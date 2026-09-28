"""Resolución de fuentes: qué archivo se lee para cada Elemento.

Orden:
1. La copia materializada en su minuto, si existe.
2. Si todavía no se guardó: el horneado de su Pieza (mismo contenido).
3. Si se colocó directo desde un Bruto: el Bruto.
4. Nada: fuera de línea (None).

Para audio separado (extensión .wav de una Pieza de video) sin materializar,
se lee el audio del horneado de la Pieza, que es el mismo sonido.

Trabaja sobre una instantánea del Taller: se puede usar en hilos de fondo.
"""

from __future__ import annotations

import copy
from pathlib import Path

from editor.core.modelo.elemento import Elemento, TipoFuente
from editor.core.modelo.proyecto import Proyecto
from editor.core.modelo.taller import Taller
from editor.core.proyecto_fs import estructura


class ResolutorFuentes:
    def __init__(self, raiz: Path, taller: Taller) -> None:
        self.raiz = raiz
        self.taller = taller

    @classmethod
    def desde(cls, proyecto: Proyecto) -> "ResolutorFuentes":
        """Con una copia del Taller: seguro para tareas de fondo."""
        assert proyecto.raiz is not None
        return cls(proyecto.raiz, copy.deepcopy(proyecto.taller))

    def __call__(self, elemento: Elemento) -> Path | None:
        if elemento.archivo is not None and elemento.archivo.exists():
            return elemento.archivo
        if elemento.fuente.tipo is TipoFuente.PIEZA:
            pieza = self.taller.piezas.get(elemento.fuente.ref)
            if pieza is not None and pieza.horneado is not None:
                ruta = estructura.ruta_horneado(self.raiz, pieza)
                if ruta is not None and ruta.exists():
                    return ruta
                if pieza.horneado.archivo is not None and pieza.horneado.archivo.exists():
                    return pieza.horneado.archivo
        elif elemento.fuente.tipo is TipoFuente.BRUTO:
            bruto = self.taller.brutos.get(elemento.fuente.ref)
            if bruto is not None:
                ruta = estructura.ruta_bruto(self.raiz, bruto)
                if ruta.exists():
                    return ruta
        return None
