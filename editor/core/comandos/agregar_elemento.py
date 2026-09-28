"""Colocar Elementos: agregar, duplicar y pegar.

Modos de colocación:
- RECHAZAR: si choca con otro de su capa, no se hace.
- SOBRESCRIBIR: recorta, divide o quita lo que tapa en su capa.
- INSERTAR: divide lo que cruza el punto en su capa y corre hacia la derecha
  todo lo que empieza después (dentro del alcance).
"""

from __future__ import annotations

import copy

from editor.core.comandos.comando import EdicionCapitulo
from editor.core.comandos.operaciones import (
    Alcance,
    ModoColocacion,
    a_desplazar,
    abrir_hueco,
    desplazar,
    dividir,
    elementos_en_capa,
)
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.proyecto import Proyecto


def colocar_con_modo(
    comando: EdicionCapitulo,
    proyecto: Proyecto,
    capitulo: Capitulo,
    nuevos: list[Elemento],
    modo: ModoColocacion,
    alcance: Alcance = Alcance.MINUTO,
    ignorar: set[str] | None = None,
) -> set[str]:
    """Coloca `nuevos` (fuera del capítulo) según el modo. Devuelve los IDs creados al dividir."""
    ignorar = set(ignorar or set()) | {e.id for e in nuevos}
    creados: set[str] = set()
    modificados: list[Elemento] = []

    if modo is ModoColocacion.SOBRESCRIBIR:
        for nuevo in nuevos:
            cambiados, _, partidos = abrir_hueco(
                capitulo, nuevo.capa, nuevo.en_global, nuevo.inicio, nuevo.fin, lambda: comando.ids.nuevo(proyecto), ignorar
            )
            modificados += cambiados + partidos
            creados |= {e.id for e in partidos}
        comando.colocar(capitulo, modificados)

    elif modo is ModoColocacion.INSERTAR:
        punto = min(n.inicio for n in nuevos)
        duracion = max(n.fin for n in nuevos) - punto
        minuto = nuevos[0].minuto_inicio
        partidos: list[Elemento] = []
        for nuevo in nuevos:
            for existente in elementos_en_capa(capitulo, nuevo.capa, nuevo.en_global):
                if existente.id not in ignorar and existente.inicio < punto < existente.fin:
                    comando.obtener(capitulo, existente.id)
                    comando.retirar(capitulo, [existente])
                    derecha = dividir(existente, punto, comando.ids.nuevo(proyecto))
                    modificados.append(existente)
                    partidos.append(derecha)
                    creados.add(derecha.id)
        comando.colocar(capitulo, modificados)
        mover = [e for e in a_desplazar(capitulo, punto, alcance, minuto, ignorar=ignorar)]
        for elemento in mover:
            comando.obtener(capitulo, elemento.id)
        comando.retirar(capitulo, mover)
        desplazar(mover + partidos, duracion)
        comando.colocar(capitulo, mover + partidos)

    comando.colocar(capitulo, nuevos)
    return creados


class AgregarElemento(EdicionCapitulo):
    descripcion = "Agregar elemento"

    def __init__(
        self,
        capitulo: int,
        elemento: Elemento,
        modo: ModoColocacion = ModoColocacion.RECHAZAR,
        alcance: Alcance = Alcance.MINUTO,
    ) -> None:
        super().__init__(capitulo)
        self.elemento = copy.deepcopy(elemento)
        self.modo = modo
        self.alcance = alcance
        self.ids_propios = {elemento.id}

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        if self.modo is ModoColocacion.RECHAZAR:
            return set()
        if self.modo is ModoColocacion.SOBRESCRIBIR:
            return {e.id for e in elementos_en_capa(capitulo, self.elemento.capa, self.elemento.en_global)
                    if e.inicio < self.elemento.fin and self.elemento.inicio < e.fin}
        return {e.id for e in capitulo.todos_los_elementos() if e.fin > self.elemento.inicio}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        nuevo = copy.deepcopy(self.elemento)
        proyecto.ids.registrar(nuevo.id)
        creados = colocar_con_modo(self, proyecto, capitulo, [nuevo], self.modo, self.alcance)
        return creados | {nuevo.id}


class PegarElementos(EdicionCapitulo):
    """Pega copias (del portapapeles de la app) con IDs nuevos, desplazadas `delta` fotogramas."""

    descripcion = "Pegar"

    def __init__(
        self,
        capitulo: int,
        elementos: list[Elemento],
        delta: int,
        modo: ModoColocacion = ModoColocacion.RECHAZAR,
    ) -> None:
        super().__init__(capitulo)
        self.elementos = [copy.deepcopy(e) for e in elementos]
        self.delta = delta
        self.modo = modo

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        if self.modo is ModoColocacion.RECHAZAR:
            return set()
        inicio = min(e.inicio for e in self.elementos) + self.delta
        return {e.id for e in capitulo.todos_los_elementos() if e.fin > inicio}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        nuevos = []
        for original in self.elementos:
            nuevo = copy.deepcopy(original)
            nuevo.id = self.ids.nuevo(proyecto)
            nuevo.archivo = None
            nuevo.tiempo.inicio += self.delta
            nuevos.append(nuevo)
        creados = colocar_con_modo(self, proyecto, capitulo, nuevos, self.modo)
        return creados | {n.id for n in nuevos}


class DuplicarElemento(PegarElementos):
    descripcion = "Duplicar elemento"

    def __init__(self, capitulo: int, elemento: Elemento, nuevo_inicio: int,
                 modo: ModoColocacion = ModoColocacion.RECHAZAR) -> None:
        super().__init__(capitulo, [elemento], nuevo_inicio - elemento.inicio, modo)
