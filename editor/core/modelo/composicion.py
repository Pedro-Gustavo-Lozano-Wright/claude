"""Composición: una línea de tiempo con Elementos en capas.

Minuto y Global son composiciones sobre la rejilla del capítulo
(PROJECT.md, 5.1). La composición guarda los Elementos y aplica la regla de
no solapamiento dentro de una capa (6.6); el capítulo aplica esa misma regla
entre minutos, porque un Elemento puede desbordarse al minuto siguiente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from editor.core.modelo.capa import Capa
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.errores import NoEncontrado, Solapamiento


def solape_permitido(anterior: Elemento, siguiente: Elemento) -> int:
    """Fotogramas que `siguiente` puede solaparse con `anterior`: la duración de su transición."""
    if siguiente.transicion_entrada is None:
        return 0
    return siguiente.transicion_entrada.duracion


def buscar_solape(nuevo: Elemento, candidatos: Iterable[Elemento]) -> Elemento | None:
    """Primer Elemento de la misma capa que choca con `nuevo`, respetando transiciones."""
    for existente in candidatos:
        if existente.id == nuevo.id or existente.capa != nuevo.capa:
            continue
        if nuevo.fin <= existente.inicio or existente.fin <= nuevo.inicio:
            continue
        if existente.inicio <= nuevo.inicio:
            anterior, siguiente = existente, nuevo
        else:
            anterior, siguiente = nuevo, existente
        solape = anterior.fin - siguiente.inicio
        contenido = siguiente.fin <= anterior.fin
        if contenido or solape > solape_permitido(anterior, siguiente):
            return existente
    return None


def clave_apilado(elemento: Elemento) -> tuple[int, int]:
    orden = elemento.orden_apilado
    return (orden if orden is not None else 0, elemento.inicio)


@dataclass
class Composicion:
    """Conjunto de Elementos sobre un rango [inicio, inicio + duracion) del capítulo."""

    inicio: int
    duracion: int
    elementos: dict[str, Elemento] = field(default_factory=dict)

    @property
    def fin(self) -> int:
        return self.inicio + self.duracion

    def __iter__(self) -> Iterator[Elemento]:
        return iter(self.elementos.values())

    def __len__(self) -> int:
        return len(self.elementos)

    def __contains__(self, id_elemento: object) -> bool:
        return id_elemento in self.elementos

    @property
    def vacia(self) -> bool:
        return not self.elementos

    def obtener(self, id_elemento: str) -> Elemento:
        try:
            return self.elementos[id_elemento]
        except KeyError:
            raise NoEncontrado(f"No hay un Elemento {id_elemento} en esta composición.") from None

    def validar_ubicacion(self, elemento: Elemento) -> None:
        """Reglas propias del tipo de composición; las subclases la amplían."""

    def agregar(self, elemento: Elemento, candidatos_solape: Iterable[Elemento] | None = None) -> None:
        self.validar_ubicacion(elemento)
        conflicto = buscar_solape(elemento, candidatos_solape if candidatos_solape is not None else self)
        if conflicto is not None:
            raise Solapamiento(elemento.id, conflicto.id, elemento.capa.codigo)
        self.elementos[elemento.id] = elemento

    def quitar(self, id_elemento: str) -> Elemento:
        elemento = self.obtener(id_elemento)
        del self.elementos[id_elemento]
        return elemento

    def en_capa(self, capa: Capa) -> list[Elemento]:
        return sorted((e for e in self if e.capa == capa), key=lambda e: e.inicio)

    def capas_usadas(self) -> list[Capa]:
        return sorted({e.capa for e in self}, key=lambda c: (c.tipo.value, c.numero))

    def en_rango(self, inicio: int, fin: int) -> list[Elemento]:
        """Elementos que tocan [inicio, fin)."""
        return [e for e in self if e.inicio < fin and inicio < e.fin]

    def visuales_activos_en(self, f: int) -> list[Elemento]:
        """Elementos visibles en f, de abajo hacia arriba."""
        return sorted((e for e in self if e.es_visual and e.activo_en(f)), key=clave_apilado)

    def sonoros_activos_en(self, f: int) -> list[Elemento]:
        return [e for e in self if e.suena and e.activo_en(f)]
