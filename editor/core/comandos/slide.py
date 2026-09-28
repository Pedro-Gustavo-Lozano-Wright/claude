"""Slide: mover un Elemento ajustando a sus vecinos contiguos.

El contenido del Elemento no cambia. El vecino anterior (que terminaba justo
donde empezaba) se alarga o acorta por su salida; el siguiente (que empezaba
justo donde terminaba) por su entrada. Valor absoluto: el nuevo inicio.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.comandos.operaciones import elementos_en_capa, recortar_fin, recortar_inicio
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.proyecto import Proyecto


class Slide(EdicionCapitulo):
    descripcion = "Slide"

    def __init__(self, capitulo: int, id_elemento: str, nuevo_inicio: int) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.nuevo_inicio = nuevo_inicio
        self._vecinos: tuple[str | None, str | None] | None = None

    def clave_fusion(self) -> tuple | None:
        return ("slide", self.id_elemento)

    def _buscar_vecinos(self, capitulo: Capitulo) -> tuple[Elemento | None, Elemento | None]:
        elemento = capitulo.obtener(self.id_elemento)
        anterior = siguiente = None
        for otro in elementos_en_capa(capitulo, elemento.capa, elemento.en_global):
            if otro.id == elemento.id:
                continue
            if otro.fin == elemento.inicio:
                anterior = otro
            elif otro.inicio == elemento.fin:
                siguiente = otro
        return anterior, siguiente

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        # Los vecinos se fijan la primera vez: al rehacer (o fusionar) son los mismos.
        if self._vecinos is None:
            anterior, siguiente = self._buscar_vecinos(capitulo)
            self._vecinos = (anterior.id if anterior else None, siguiente.id if siguiente else None)
        return {self.id_elemento} | {i for i in self._vecinos if i}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        assert self._vecinos is not None
        elemento = self.obtener(capitulo, self.id_elemento)
        anterior = self.obtener(capitulo, self._vecinos[0]) if self._vecinos[0] else None
        siguiente = self.obtener(capitulo, self._vecinos[1]) if self._vecinos[1] else None
        delta = self.nuevo_inicio - elemento.inicio
        if delta == 0:
            return set()
        grupo = [e for e in (anterior, elemento, siguiente) if e is not None]
        self.retirar(capitulo, grupo)
        if anterior is not None:
            recortar_fin(anterior, anterior.fin + delta)
        if siguiente is not None:
            nuevo = siguiente.inicio + delta
            if nuevo >= siguiente.fin:
                raise EdicionRechazada("El vecino siguiente se quedaría sin duración.")
            recortar_inicio(siguiente, nuevo)
        elemento.tiempo.inicio = self.nuevo_inicio
        self.colocar(capitulo, grupo)
        return set()
