"""Índice de referencias: Bruto → Piezas → Elementos → Minutos.

Sirve para saber qué copias materializadas hay que actualizar cuando se
vuelve a hornear una Pieza, qué depende de algo antes de borrarlo y qué
minutos invalidar. Se reconstruye al abrir el proyecto y se mantiene al día
con `registrar` y `olvidar`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from editor.core.modelo.elemento import Elemento, TipoFuente

if TYPE_CHECKING:
    from editor.core.modelo.proyecto import Proyecto


@dataclass(frozen=True)
class Ubicacion:
    capitulo: int
    minuto: int | None  # None = Global


@dataclass
class IndiceReferencias:
    piezas_por_bruto: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    elementos_por_fuente: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    ubicaciones: dict[str, Ubicacion] = field(default_factory=dict)

    def reconstruir(self, proyecto: "Proyecto") -> None:
        self.piezas_por_bruto.clear()
        self.elementos_por_fuente.clear()
        self.ubicaciones.clear()
        for pieza in proyecto.taller.piezas.values():
            for id_bruto in pieza.ids_brutos():
                self.piezas_por_bruto[id_bruto].add(pieza.id)
        for capitulo in proyecto.capitulos.values():
            for elemento in capitulo.todos_los_elementos():
                self.registrar(elemento, capitulo.numero)

    def registrar(self, elemento: Elemento, capitulo: int) -> None:
        self.olvidar(elemento.id)
        if elemento.fuente.tipo is not TipoFuente.TEXTO and elemento.fuente.ref:
            self.elementos_por_fuente[elemento.fuente.ref].add(elemento.id)
        minuto = None if elemento.en_global else elemento.minuto_inicio
        self.ubicaciones[elemento.id] = Ubicacion(capitulo, minuto)

    def olvidar(self, id_elemento: str) -> None:
        self.ubicaciones.pop(id_elemento, None)
        for elementos in self.elementos_por_fuente.values():
            elementos.discard(id_elemento)

    def registrar_pieza(self, id_pieza: str, ids_brutos: set[str]) -> None:
        for piezas in self.piezas_por_bruto.values():
            piezas.discard(id_pieza)
        for id_bruto in ids_brutos:
            self.piezas_por_bruto[id_bruto].add(id_pieza)

    # --- Consultas -------------------------------------------------------------

    def piezas_de_bruto(self, id_bruto: str) -> set[str]:
        return set(self.piezas_por_bruto.get(id_bruto, ()))

    def elementos_de_fuente(self, id_fuente: str) -> set[str]:
        """Elementos que son copias de una Pieza (o que usan un Bruto directamente)."""
        return set(self.elementos_por_fuente.get(id_fuente, ()))

    def ubicacion(self, id_elemento: str) -> Ubicacion | None:
        return self.ubicaciones.get(id_elemento)

    def ubicaciones_de_fuente(self, id_fuente: str) -> set[Ubicacion]:
        return {
            self.ubicaciones[id_elemento]
            for id_elemento in self.elementos_de_fuente(id_fuente)
            if id_elemento in self.ubicaciones
        }

    def dependientes_de_bruto(self, id_bruto: str) -> tuple[set[str], set[str]]:
        """(Piezas, Elementos) que dependen de un Bruto."""
        piezas = self.piezas_de_bruto(id_bruto)
        elementos = self.elementos_de_fuente(id_bruto)
        for id_pieza in piezas:
            elementos |= self.elementos_de_fuente(id_pieza)
        return piezas, elementos
