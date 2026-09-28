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
