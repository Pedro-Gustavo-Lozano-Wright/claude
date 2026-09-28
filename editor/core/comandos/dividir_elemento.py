"""Dividir Elementos en un fotograma (cuchilla).

Sin IDs explícitos corta todo lo editable que pasa por ese fotograma, en
minutos y en Global.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo
from editor.core.comandos.operaciones import dividir
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class DividirElementos(EdicionCapitulo):
    descripcion = "Dividir"

    def __init__(self, capitulo: int, f: int, ids: list[str] | None = None) -> None:
        super().__init__(capitulo)
        self.f = f
        self.ids_dividir = ids

    def _objetivo(self, capitulo: Capitulo) -> list[str]:
        if self.ids_dividir is not None:
            return list(self.ids_dividir)
        return [
            e.id for e in capitulo.todos_los_elementos()
            if e.inicio < self.f < e.fin and capitulo.editable(e)
        ]

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return set(self._objetivo(capitulo))

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        izquierdas = [self.obtener(capitulo, i) for i in sorted(self._objetivo(capitulo))]
        self.retirar(capitulo, izquierdas)
        derechas = [dividir(e, self.f, self.ids.nuevo(proyecto)) for e in izquierdas]
        self.colocar(capitulo, izquierdas + derechas)
        return {d.id for d in derechas}
