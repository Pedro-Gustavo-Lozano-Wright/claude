"""Agregar efectos, cambiar sus parámetros y reordenarlos (T6.5)."""

from __future__ import annotations

import copy

from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.efecto import Efecto, es_tipo_efecto
from editor.core.modelo.proyecto import Proyecto


class AgregarEfecto(EdicionCapitulo):
    descripcion = "Agregar efecto"

    def __init__(self, capitulo: int, id_elemento: str, efecto: Efecto, indice: int | None = None) -> None:
        super().__init__(capitulo)
        if not es_tipo_efecto(efecto.tipo):
            raise ValueError(f"Efecto desconocido: {efecto.tipo!r}")
        self.id_elemento = id_elemento
        self.efecto = copy.deepcopy(efecto)
        self.indice = indice

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        if not elemento.es_visual:
            raise EdicionRechazada("Los efectos de imagen solo van en capas V o T.")
        posicion = len(elemento.efectos) if self.indice is None else self.indice
        elemento.efectos.insert(posicion, copy.deepcopy(self.efecto))
        return set()


class CambiarParametroEfecto(EdicionCapitulo):
    descripcion = "Ajustar efecto"

    def __init__(self, capitulo: int, id_elemento: str, indice: int, parametro: str, valor: float) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.indice = indice
        self.parametro = parametro
        self.valor = valor

    def clave_fusion(self) -> tuple | None:
        return ("efecto", self.id_elemento, self.indice, self.parametro)

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        try:
            efecto = elemento.efectos[self.indice]
        except IndexError:
            raise EdicionRechazada(f"No hay un efecto en la posición {self.indice}.") from None
        efecto.parametros[self.parametro] = float(self.valor)
        return set()


class ActivarEfecto(EdicionCapitulo):
    descripcion = "Activar o desactivar efecto"

    def __init__(self, capitulo: int, id_elemento: str, indice: int, activo: bool) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.indice = indice
        self.activo = activo

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        try:
            elemento.efectos[self.indice].activo = self.activo
        except IndexError:
            raise EdicionRechazada(f"No hay un efecto en la posición {self.indice}.") from None
        return set()


class ReordenarEfecto(EdicionCapitulo):
    descripcion = "Reordenar efectos"

    def __init__(self, capitulo: int, id_elemento: str, desde: int, hacia: int) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.desde = desde
        self.hacia = hacia

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        cantidad = len(elemento.efectos)
        if not (0 <= self.desde < cantidad and 0 <= self.hacia < cantidad):
            raise EdicionRechazada("Posición de efecto fuera de rango.")
        elemento.efectos.insert(self.hacia, elemento.efectos.pop(self.desde))
        return set()
