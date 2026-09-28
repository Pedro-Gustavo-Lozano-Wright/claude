"""Definir o quitar la transición de entrada de un Elemento.

La transición permite solapar al Elemento con el anterior de su capa durante
su duración; al cambiarla se vuelve a validar el solape.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto
from editor.core.modelo.transicion import Transicion


class CambiarTransicion(EdicionCapitulo):
    descripcion = "Cambiar transición"

    def __init__(self, capitulo: int, id_elemento: str, transicion: Transicion | None) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.transicion = transicion

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        self.retirar(capitulo, [elemento])
        elemento.transicion_entrada = self.transicion
        self.colocar(capitulo, [elemento])
        return set()
