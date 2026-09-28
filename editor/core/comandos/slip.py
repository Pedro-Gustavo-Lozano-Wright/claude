"""Slip: cambiar qué parte de la fuente se ve sin mover el Elemento.

Valor absoluto (la nueva entrada de la fuente); el límite es el material que
tiene la fuente, asas incluidas (`margen_fuente`).
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class Slip(EdicionCapitulo):
    descripcion = "Slip"

    def __init__(self, capitulo: int, id_elemento: str, nueva_entrada: int) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.nueva_entrada = nueva_entrada

    def clave_fusion(self) -> tuple | None:
        return ("slip", self.id_elemento)

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        if self.nueva_entrada < 0:
            raise EdicionRechazada("No hay material de la fuente antes del fotograma 0.")
        anterior = elemento.tiempo.fuente_entrada
        elemento.tiempo.fuente_entrada = self.nueva_entrada
        if elemento.excede_fuente:
            elemento.tiempo.fuente_entrada = anterior
            raise EdicionRechazada("No hay suficiente material en la fuente para ese desplazamiento.")
        return set()
