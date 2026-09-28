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


class RecortarElementos(EdicionCapitulo):
    """Recorte en grupo (selección múltiple): el mismo lado de cada Elemento a su borde absoluto.

    Se aplica todo o nada; los arrastres se fusionan en un solo paso de deshacer.
    """

    descripcion = "Recortar elementos"

    def __init__(self, capitulo: int, lado: str, bordes: dict[str, int]) -> None:
        super().__init__(capitulo)
        if lado not in (INICIO, FIN):
            raise ValueError(f"Lado desconocido: {lado!r}")
        if not bordes:
            raise ValueError("No hay Elementos que recortar.")
        self.lado = lado
        self.bordes = dict(bordes)

    def clave_fusion(self) -> tuple | None:
        return ("recortar-grupo", self.lado, tuple(sorted(self.bordes)))

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return set(self.bordes)

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elementos = [self.obtener(capitulo, identificador) for identificador in self.bordes]
        self.retirar(capitulo, elementos)
        for elemento in elementos:
            if self.lado == INICIO:
                recortar_inicio(elemento, self.bordes[elemento.id])
            else:
                recortar_fin(elemento, self.bordes[elemento.id])
        self.colocar(capitulo, elementos)
        return set()
