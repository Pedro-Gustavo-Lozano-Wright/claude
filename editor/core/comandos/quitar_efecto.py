"""Quitar un efecto de la pila de un Elemento (T6.5)."""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class QuitarEfecto(EdicionCapitulo):
    descripcion = "Quitar efecto"

    def __init__(self, capitulo: int, id_elemento: str, indice: int) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.indice = indice

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        if not 0 <= self.indice < len(elemento.efectos):
            raise EdicionRechazada(f"No hay un efecto en la posición {self.indice}.")
        del elemento.efectos[self.indice]
        return set()
