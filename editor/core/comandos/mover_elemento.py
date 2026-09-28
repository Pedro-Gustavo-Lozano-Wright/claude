"""Mover Elementos en el tiempo, de capa, de minuto o de capítulo (T6.4).

`MoverElemento` usa valores absolutos: los arrastres se fusionan en un solo
paso de deshacer.
"""

from __future__ import annotations

import copy

from editor.core.comandos.agregar_elemento import AgregarElemento, colocar_con_modo
from editor.core.comandos.comando import EdicionCapitulo
from editor.core.comandos.compuesto import ComandoCompuesto
from editor.core.comandos.operaciones import Alcance, ModoColocacion, elementos_en_capa
from editor.core.comandos.quitar_elemento import QuitarElementos
from editor.core.modelo.capa import Capa
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.errores import ErrorModelo
from editor.core.modelo.proyecto import Proyecto


class MoverElemento(EdicionCapitulo):
    descripcion = "Mover elemento"

    def __init__(
        self,
        capitulo: int,
        id_elemento: str,
        nuevo_inicio: int,
        nueva_capa: Capa | None = None,
        modo: ModoColocacion = ModoColocacion.RECHAZAR,
        alcance: Alcance = Alcance.MINUTO,
    ) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.nuevo_inicio = nuevo_inicio
        self.nueva_capa = nueva_capa
        self.modo = modo
        self.alcance = alcance

    def clave_fusion(self) -> tuple | None:
        return ("mover", self.id_elemento, self.modo) if self.modo is ModoColocacion.RECHAZAR else None

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        ids = {self.id_elemento}
        elemento = capitulo.buscar(self.id_elemento)
        if elemento is None or self.modo is ModoColocacion.RECHAZAR:
            return ids
        fin = self.nuevo_inicio + elemento.duracion
        capa = self.nueva_capa or elemento.capa
        if self.modo is ModoColocacion.SOBRESCRIBIR:
            return ids | {e.id for e in elementos_en_capa(capitulo, capa, elemento.en_global)
                          if e.inicio < fin and self.nuevo_inicio < e.fin}
        return ids | {e.id for e in capitulo.todos_los_elementos() if e.fin > self.nuevo_inicio}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        if self.nueva_capa is not None and self.nueva_capa.tipo is not elemento.capa.tipo:
            raise ErrorModelo("Un Elemento solo cambia a otra capa de su mismo tipo (V, A o T).")
        self.retirar(capitulo, [elemento])
        elemento.tiempo.inicio = self.nuevo_inicio
        if self.nueva_capa is not None:
            elemento.capa = self.nueva_capa
        return colocar_con_modo(self, proyecto, capitulo, [elemento], self.modo, self.alcance)


class MoverElementos(EdicionCapitulo):
    """Mueve varios Elementos a la vez (selección múltiple), cada uno a su inicio absoluto.

    Valores absolutos por Elemento: los arrastres se fusionan en un solo paso de
    deshacer. Cada uno conserva su capa; se validan todos juntos.
    """

    descripcion = "Mover elementos"

    def __init__(self, capitulo: int, destinos: dict[str, int]) -> None:
        super().__init__(capitulo)
        if not destinos:
            raise ValueError("No hay Elementos que mover.")
        if any(inicio < 0 for inicio in destinos.values()):
            raise ValueError("Un Elemento no puede empezar antes de 00:00.")
        self.destinos = dict(destinos)

    def clave_fusion(self) -> tuple | None:
        return ("mover-grupo", tuple(sorted(self.destinos)))

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return set(self.destinos)

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elementos = [self.obtener(capitulo, identificador) for identificador in self.destinos]
        self.retirar(capitulo, elementos)
        for elemento in elementos:
            elemento.tiempo.inicio = self.destinos[elemento.id]
        return colocar_con_modo(self, proyecto, capitulo, elementos, ModoColocacion.RECHAZAR, Alcance.MINUTO)


class CambiarAGlobal(EdicionCapitulo):
    """Pasa un Elemento de los minutos a Global o al revés, en el mismo instante y capa.

    Global es para lo que abarca varios minutos (música, un logo fijo); al guardar,
    el gemelo y el archivo cambian de carpeta como en cualquier otro movimiento.
    """

    def __init__(self, capitulo: int, id_elemento: str, a_global: bool) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.a_global = a_global
        self.descripcion = "Pasar a Global" if a_global else "Pasar a los minutos"

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        if elemento.en_global == self.a_global:
            return set()
        self.retirar(capitulo, [elemento])
        elemento.en_global = self.a_global
        return colocar_con_modo(self, proyecto, capitulo, [elemento], ModoColocacion.RECHAZAR, Alcance.MINUTO)


def mover_entre_capitulos(
    proyecto: Proyecto,
    origen: int,
    destino: int,
    id_elemento: str,
    nuevo_inicio: int,
    nueva_capa: Capa | None = None,
    modo: ModoColocacion = ModoColocacion.RECHAZAR,
) -> ComandoCompuesto:
    """Quitar del capítulo de origen y agregar en el de destino, conservando el ID."""
    elemento = copy.deepcopy(proyecto.capitulo(origen).obtener(id_elemento))
    elemento.tiempo.inicio = nuevo_inicio
    elemento.archivo = None
    if nueva_capa is not None:
        elemento.capa = nueva_capa
    return ComandoCompuesto(
        "Mover a otro capítulo",
        [QuitarElementos(origen, [id_elemento]), AgregarElemento(destino, elemento, modo)],
    )
