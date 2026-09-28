"""Keyframes: valores de un parámetro a lo largo del tiempo.

Los fotogramas de un keyframe son **relativos al inicio del Elemento** (o del
Short), así que mover el Elemento no obliga a reescribirlos.
La curva de un keyframe gobierna el tramo que va desde él hasta el siguiente.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from editor.core.utiles.interpolacion import LINEAL, NOMBRES_CURVAS, interpolar


@dataclass(frozen=True)
class Keyframe:
    f: int
    valor: float
    curva: str = LINEAL
    controles: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        if self.f < 0:
            raise ValueError(f"Keyframe en fotograma negativo: {self.f}")
        if self.curva not in NOMBRES_CURVAS:
            raise ValueError(f"Curva desconocida: {self.curva!r}")


@dataclass
class PistaKeyframes:
    """Keyframes de un solo parámetro, ordenados por fotograma."""

    keyframes: list[Keyframe] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.keyframes.sort(key=lambda k: k.f)

    def __iter__(self) -> Iterator[Keyframe]:
        return iter(self.keyframes)

    def __len__(self) -> int:
        return len(self.keyframes)

    @property
    def vacia(self) -> bool:
        return not self.keyframes

    def _indice(self, f: int) -> int | None:
        posiciones = [k.f for k in self.keyframes]
        indice = bisect.bisect_left(posiciones, f)
        if indice < len(self.keyframes) and self.keyframes[indice].f == f:
            return indice
        return None

    def obtener(self, f: int) -> Keyframe | None:
        indice = self._indice(f)
        return self.keyframes[indice] if indice is not None else None

    def poner(self, keyframe: Keyframe) -> Keyframe | None:
        """Agrega o reemplaza el keyframe de ese fotograma. Devuelve el reemplazado."""
        indice = self._indice(keyframe.f)
        if indice is not None:
            anterior = self.keyframes[indice]
            self.keyframes[indice] = keyframe
            return anterior
        bisect.insort(self.keyframes, keyframe, key=lambda k: k.f)
        return None

    def quitar(self, f: int) -> Keyframe | None:
        indice = self._indice(f)
        return self.keyframes.pop(indice) if indice is not None else None

    def valor_en(self, f: float, base: float) -> float:
        """Valor en el fotograma f (puede ser fraccionario). Sin keyframes, `base`."""
        if not self.keyframes:
            return base
        if f <= self.keyframes[0].f:
            return self.keyframes[0].valor
        if f >= self.keyframes[-1].f:
            return self.keyframes[-1].valor
        posiciones = [k.f for k in self.keyframes]
        indice = bisect.bisect_right(posiciones, f) - 1
        izquierda, derecha = self.keyframes[indice], self.keyframes[indice + 1]
        t = (f - izquierda.f) / (derecha.f - izquierda.f)
        return interpolar(izquierda.valor, derecha.valor, t, izquierda.curva, izquierda.controles)

    def desplazada(self, delta: int, desde: int = 0, hasta: int | None = None) -> "PistaKeyframes":
        """Copia con los fotogramas en [desde, hasta) movidos `delta` (para dividir Elementos)."""
        resultado = [
            Keyframe(k.f + delta, k.valor, k.curva, k.controles)
            for k in self.keyframes
            if k.f >= desde and (hasta is None or k.f < hasta) and k.f + delta >= 0
        ]
        return PistaKeyframes(resultado)


@dataclass
class Animacion:
    """Pistas de keyframes por nombre de parámetro."""

    pistas: dict[str, PistaKeyframes] = field(default_factory=dict)

    def pista(self, propiedad: str) -> PistaKeyframes:
        """Pista de una propiedad, creándola si no existe."""
        return self.pistas.setdefault(propiedad, PistaKeyframes())

    def tiene(self, propiedad: str) -> bool:
        pista = self.pistas.get(propiedad)
        return pista is not None and not pista.vacia

    def valor(self, propiedad: str, f: float, base: float) -> float:
        pista = self.pistas.get(propiedad)
        return base if pista is None else pista.valor_en(f, base)

    def valores(self, f: float, bases: dict[str, float]) -> dict[str, float]:
        """Evalúa solo las propiedades animadas; las demás no aparecen en el resultado."""
        return {
            propiedad: pista.valor_en(f, bases.get(propiedad, 0.0))
            for propiedad, pista in self.pistas.items()
            if not pista.vacia and propiedad in bases
        }

    def propiedades(self) -> Iterable[str]:
        return (propiedad for propiedad, pista in self.pistas.items() if not pista.vacia)

    def limpiar_vacias(self) -> None:
        for propiedad in [p for p, pista in self.pistas.items() if pista.vacia]:
            del self.pistas[propiedad]

    def desplazada(self, delta: int, desde: int = 0, hasta: int | None = None) -> "Animacion":
        return Animacion({
            propiedad: pista.desplazada(delta, desde, hasta) for propiedad, pista in self.pistas.items()
        })

    def copia(self) -> "Animacion":
        return self.desplazada(0)
