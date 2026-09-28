"""Quitar Elementos, con o sin ripple (T6.4).

Con ripple, lo que viene después **en la misma capa** se corre hacia la
izquierda para cerrar el hueco, dentro del alcance elegido.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo
from editor.core.comandos.operaciones import Alcance, a_desplazar, desplazar
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class QuitarElementos(EdicionCapitulo):
    descripcion = "Quitar"

    def __init__(self, capitulo: int, ids: list[str], ripple: bool = False, alcance: Alcance = Alcance.MINUTO) -> None:
        super().__init__(capitulo)
        self.ids_quitar = list(dict.fromkeys(ids))
        self.ripple = ripple
        self.alcance = alcance
        if ripple:
            self.descripcion = "Quitar con ripple"

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        ids = set(self.ids_quitar)
        if self.ripple:
            for identificador in self.ids_quitar:
                elemento = capitulo.buscar(identificador)
                if elemento is not None and not elemento.en_global:
                    ids |= {e.id for e in a_desplazar(capitulo, elemento.fin, self.alcance,
                                                      elemento.minuto_inicio, elemento.capa)}
        return ids

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        quitados = [self.obtener(capitulo, i) for i in self.ids_quitar]
        self.retirar(capitulo, quitados)
        if self.ripple:
            # De derecha a izquierda, para que cada hueco se cierre con lo que realmente sigue.
            for quitado in sorted((q for q in quitados if not q.en_global), key=lambda e: e.inicio, reverse=True):
                siguientes = a_desplazar(capitulo, quitado.fin, self.alcance, quitado.minuto_inicio, quitado.capa)
                for elemento in siguientes:
                    self.obtener(capitulo, elemento.id)
                self.retirar(capitulo, siguientes)
                desplazar(siguientes, -quitado.duracion)
                self.colocar(capitulo, siguientes)
        return set()
