"""Roll: mover el corte entre dos Elementos contiguos de la misma capa.

La duración total no cambia: lo que gana uno lo pierde el otro. Valor
absoluto (el nuevo punto de corte), así que los arrastres se fusionan.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.comandos.operaciones import mismo_espacio, recortar_fin, recortar_inicio
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class Roll(EdicionCapitulo):
    descripcion = "Roll"

    def __init__(self, capitulo: int, id_izquierdo: str, id_derecho: str, nuevo_corte: int) -> None:
        super().__init__(capitulo)
        self.id_izquierdo = id_izquierdo
        self.id_derecho = id_derecho
        self.nuevo_corte = nuevo_corte

    def clave_fusion(self) -> tuple | None:
        return ("roll", self.id_izquierdo, self.id_derecho)

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_izquierdo, self.id_derecho}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        izquierdo = self.obtener(capitulo, self.id_izquierdo)
        derecho = self.obtener(capitulo, self.id_derecho)
        if not mismo_espacio(izquierdo, derecho) or izquierdo.fin != derecho.inicio:
            raise EdicionRechazada("El roll necesita dos Elementos contiguos de la misma capa.")
        if not izquierdo.inicio < self.nuevo_corte < derecho.fin:
            raise EdicionRechazada("El corte debe quedar dentro de los dos Elementos.")
        self.retirar(capitulo, [izquierdo, derecho])
        # Orden: primero se libera espacio, después se ocupa.
        if self.nuevo_corte < izquierdo.fin:
            recortar_fin(izquierdo, self.nuevo_corte)
            recortar_inicio(derecho, self.nuevo_corte)
        else:
            recortar_inicio(derecho, self.nuevo_corte)
            recortar_fin(izquierdo, self.nuevo_corte)
        self.colocar(capitulo, [izquierdo, derecho])
        return set()
