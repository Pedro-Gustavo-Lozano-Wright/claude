"""Taller: el sandbox donde viven los Brutos (T0) y las Piezas (T1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from editor.core.modelo.bruto import Bruto
from editor.core.modelo.errores import ErrorModelo, NoEncontrado
from editor.core.modelo.pieza import Pieza


@dataclass
class Taller:
    brutos: dict[str, Bruto] = field(default_factory=dict)
    piezas: dict[str, Pieza] = field(default_factory=dict)

    # --- Brutos ------------------------------------------------------------------

    def siguiente_numero_bruto(self) -> int:
        return max((b.numero for b in self.brutos.values()), default=0) + 1

    def agregar_bruto(self, bruto: Bruto) -> None:
        if bruto.id in self.brutos:
            raise ErrorModelo(f"Ya existe un Bruto {bruto.id}.")
        self.brutos[bruto.id] = bruto

    def bruto(self, id_bruto: str) -> Bruto:
        try:
            return self.brutos[id_bruto]
        except KeyError:
            raise NoEncontrado(f"No existe el Bruto {id_bruto}.") from None

    def quitar_bruto(self, id_bruto: str) -> Bruto:
        usan = [p.id for p in self.piezas.values() if id_bruto in p.ids_brutos()]
        if usan:
            raise ErrorModelo(f"El Bruto {id_bruto} lo usan las Piezas: {', '.join(sorted(usan))}.")
        return self.brutos.pop(self.bruto(id_bruto).id)

    # --- Piezas ------------------------------------------------------------------

    def siguiente_numero_pieza(self) -> int:
        return max((p.numero for p in self.piezas.values()), default=0) + 1

    def agregar_pieza(self, pieza: Pieza) -> None:
        if pieza.id in self.piezas:
            raise ErrorModelo(f"Ya existe una Pieza {pieza.id}.")
        faltantes = pieza.ids_brutos() - self.brutos.keys()
        if faltantes:
            raise NoEncontrado(f"La Pieza {pieza.id} usa Brutos inexistentes: {', '.join(sorted(faltantes))}.")
        self.piezas[pieza.id] = pieza

    def pieza(self, id_pieza: str) -> Pieza:
        try:
            return self.piezas[id_pieza]
        except KeyError:
            raise NoEncontrado(f"No existe la Pieza {id_pieza}.") from None

    def quitar_pieza(self, id_pieza: str) -> Pieza:
        return self.piezas.pop(self.pieza(id_pieza).id)

    def piezas_de_bruto(self, id_bruto: str) -> list[Pieza]:
        return [p for p in self.piezas.values() if id_bruto in p.ids_brutos()]
