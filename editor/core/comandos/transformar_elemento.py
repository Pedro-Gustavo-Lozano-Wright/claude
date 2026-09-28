"""Transformación espacial de un Elemento (T6.5)."""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo
from editor.core.espacio.transform import Transform
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class TransformarElemento(EdicionCapitulo):
    """Reemplaza la transformación completa (posición, escala, rotación, recorte, opacidad, mezcla)."""

    descripcion = "Transformar"

    def __init__(self, capitulo: int, id_elemento: str, transform: Transform) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.transform = transform

    def clave_fusion(self) -> tuple | None:
        return ("transformar", self.id_elemento)

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        self.obtener(capitulo, self.id_elemento).espacio = self.transform
        return set()


class MoverAncla(EdicionCapitulo):
    """Cambia el ancla sin que el Elemento se mueva en el lienzo."""

    descripcion = "Mover ancla"

    def __init__(self, capitulo: int, id_elemento: str, ancla_x: float, ancla_y: float) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.ancla_x = ancla_x
        self.ancla_y = ancla_y

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        elemento.espacio = elemento.espacio.mover_ancla(self.ancla_x, self.ancla_y)
        return set()
