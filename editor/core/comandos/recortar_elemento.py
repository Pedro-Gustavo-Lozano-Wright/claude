"""Trim: cambiar la entrada o la salida de un Elemento sin mover a los vecinos (T6.4).

Valores absolutos (el nuevo borde en fotogramas del capítulo): los arrastres
se fusionan en un solo paso.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo
from editor.core.comandos.operaciones import recortar_fin, recortar_inicio
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto

INICIO = "inicio"
FIN = "fin"


class RecortarElemento(EdicionCapitulo):
    descripcion = "Recortar"

    def __init__(self, capitulo: int, id_elemento: str, lado: str, nuevo_borde: int) -> None:
        super().__init__(capitulo)
        if lado not in (INICIO, FIN):
            raise ValueError(f"Lado desconocido: {lado!r}")
        self.id_elemento = id_elemento
        self.lado = lado
        self.nuevo_borde = nuevo_borde

    def clave_fusion(self) -> tuple | None:
        return ("recortar", self.id_elemento, self.lado)

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        self.retirar(capitulo, [elemento])
        if self.lado == INICIO:
            recortar_inicio(elemento, self.nuevo_borde)
        else:
            recortar_fin(elemento, self.nuevo_borde)
        self.colocar(capitulo, [elemento])
        return set()
