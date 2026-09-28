"""Capítulo: exactamente 24 minutos (34 560 fotogramas) más Global y Shorts.

El capítulo es la línea de tiempo real y continua; los minutos son ventanas
sobre ella (PROJECT.md, 5.2). Por eso el capítulo:

- ubica cada Elemento en el minuto donde empieza;
- aplica la regla de no solapamiento entre minutos (desbordes incluidos);
- responde qué Elementos están activos en cualquier fotograma, sin importar
  en qué carpeta viven.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from editor.core.estandar import MINUTOS_POR_CAPITULO
from editor.core.modelo.composicion import clave_apilado
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.errores import ErrorModelo, NoEncontrado
from editor.core.modelo.global_ import Global
from editor.core.modelo.marcador import EstadoCapa, Marcador, clave_capa
from editor.core.modelo.minuto import Minuto
from editor.core.modelo.short import Short
from editor.core.tiempo import granularidad
from editor.core.tiempo.nomenclatura import NombreRender, codigo_capitulo, validar_numero_capitulo


@dataclass
class RegistroRender:
    """Entregable ya producido (minuto, rango o capítulo completo)."""

    nombre: NombreRender
    huella: str


@dataclass
class Capitulo:
    numero: int
    titulo: str = ""
    minutos: list[Minuto] = field(default_factory=lambda: [Minuto.nuevo(n) for n in range(MINUTOS_POR_CAPITULO)])
    global_: Global = field(default_factory=Global.nuevo)
    shorts: dict[str, Short] = field(default_factory=dict)
    renders: list[RegistroRender] = field(default_factory=list)
    marcadores: list[Marcador] = field(default_factory=list)
    # Estado por capa: "V1" … para los minutos, "GV1" … para Global.
    capas: dict[str, EstadoCapa] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validar_numero_capitulo(self.numero)
        if len(self.minutos) != MINUTOS_POR_CAPITULO:
            raise ErrorModelo(f"Un capítulo tiene exactamente {MINUTOS_POR_CAPITULO} minutos.")

    @property
    def codigo(self) -> str:
        return codigo_capitulo(self.numero)

    def minuto(self, numero: int) -> Minuto:
        granularidad.validar_minuto(numero)
        return self.minutos[numero]

    def minuto_de(self, f: int) -> Minuto:
        return self.minuto(granularidad.minuto_de(f))

    # --- Recorrido -------------------------------------------------------------

    def elementos_de_minutos(self) -> Iterator[Elemento]:
        for minuto in self.minutos:
            yield from minuto

    def todos_los_elementos(self) -> Iterator[Elemento]:
        yield from self.elementos_de_minutos()
        yield from self.global_

    def buscar(self, id_elemento: str) -> Elemento | None:
        for elemento in self.todos_los_elementos():
            if elemento.id == id_elemento:
                return elemento
        return None

    def obtener(self, id_elemento: str) -> Elemento:
        elemento = self.buscar(id_elemento)
        if elemento is None:
            raise NoEncontrado(f"No hay un Elemento {id_elemento} en {self.codigo}.")
        return elemento

    def contenedor_de(self, elemento: Elemento) -> Minuto | Global:
        return self.global_ if elemento.en_global else self.minuto(elemento.minuto_inicio)

    # --- Edición (la usan los comandos) ----------------------------------------

    def agregar(self, elemento: Elemento) -> None:
        """Ubica el Elemento en Global o en el minuto donde empieza."""
        if elemento.en_global:
            self.global_.agregar(elemento)
            return
        if not granularidad.dentro_del_capitulo(elemento.inicio):
            raise ErrorModelo(f"El Elemento {elemento.id} empieza fuera del capítulo.")
        candidatos = self.minutos_elementos_en_rango(elemento.inicio, elemento.fin)
        self.minuto(elemento.minuto_inicio).agregar(elemento, candidatos)

    def quitar(self, id_elemento: str) -> Elemento:
        elemento = self.obtener(id_elemento)
        return self.contenedor_de(elemento).quitar(id_elemento)

    def reubicar(self, elemento: Elemento, minuto_anterior: int | None) -> None:
        """Tras cambiar el inicio de un Elemento, lo mueve al minuto que le corresponde.

        `minuto_anterior` es el minuto donde estaba guardado antes del cambio.
        """
        if elemento.en_global:
            return
        origen = self.minuto(minuto_anterior if minuto_anterior is not None else elemento.minuto_inicio)
        origen.elementos.pop(elemento.id, None)
        try:
            self.agregar(elemento)
        except Exception:
            # El comando que llamó revierte el cambio de tiempo; aquí solo se
            # devuelve el Elemento a su carpeta para no perderlo.
            origen.elementos[elemento.id] = elemento
            raise

    # --- Capas y marcadores ----------------------------------------------------

    def estado_capa(self, elemento: Elemento) -> EstadoCapa:
        return self.capas.get(clave_capa(elemento.capa.codigo, elemento.en_global), EstadoCapa())

    def _hay_solo(self) -> bool:
        return any(estado.solo for estado in self.capas.values())

    def se_ve(self, elemento: Elemento) -> bool:
        return self.estado_capa(elemento).visible

    def se_oye(self, elemento: Elemento, idioma: str | None = None) -> bool:
        """¿Suena este Elemento? Con `idioma`, solo lo común y las capas de ese idioma.

        Sin `idioma` (edición) suena todo; el render por idioma mezcla la pista
        común (música y efectos) más el diálogo de ese idioma.
        """
        estado = self.estado_capa(elemento)
        if estado.silenciada:
            return False
        if idioma is not None and estado.idioma and estado.idioma != idioma:
            return False
        return estado.solo or not self._hay_solo()

    def idiomas(self) -> list[str]:
        """Idiomas con pista propia en este capítulo."""
        return sorted({estado.idioma for estado in self.capas.values() if estado.idioma})

    def editable(self, elemento: Elemento) -> bool:
        return not elemento.estado.bloqueado and not self.estado_capa(elemento).bloqueada

    def marcadores_en_rango(self, inicio: int, fin: int) -> list[Marcador]:
        return sorted((m for m in self.marcadores if inicio <= m.f < fin), key=lambda m: m.f)

    # --- Consultas de tiempo ---------------------------------------------------

    def minutos_elementos_en_rango(self, inicio: int, fin: int) -> list[Elemento]:
        """Elementos de minutos (no Global) que tocan [inicio, fin), incluidos desbordes."""
        return [e for e in self.elementos_de_minutos() if e.inicio < fin and inicio < e.fin]

    def visuales_activos_en(self, f: int) -> list[Elemento]:
        """Todo lo visible en f: minuto actual, desbordes de minutos anteriores y Global."""
        if not granularidad.dentro_del_capitulo(f):
            return []
        candidatos = [
            e for minuto in self.minutos[: granularidad.minuto_de(f) + 1] for e in minuto
            if e.es_visual and e.activo_en(f)
        ]
        candidatos.extend(self.global_.visuales_activos_en(f))
        return sorted((e for e in candidatos if self.se_ve(e)), key=clave_apilado)

    def sonoros_activos_en(self, f: int, idioma: str | None = None) -> list[Elemento]:
        if not granularidad.dentro_del_capitulo(f):
            return []
        candidatos = [
            e for minuto in self.minutos[: granularidad.minuto_de(f) + 1] for e in minuto
            if e.suena and e.activo_en(f)
        ]
        candidatos.extend(self.global_.sonoros_activos_en(f))
        return [e for e in candidatos if self.se_oye(e, idioma)]

    def que_afecta_al_minuto(self, numero: int) -> list[Elemento]:
        """Todo lo que influye en el render de un minuto (base de su huella, PROJECT.md 13.2)."""
        inicio, fin = granularidad.rango_minuto(numero)
        return list(self.minuto(numero)) + self.desbordes_hacia(numero) + self.global_.en_rango(inicio, fin)

    def desbordes_hacia(self, numero: int) -> list[Elemento]:
        """Elementos de minutos anteriores que entran en este minuto (referencias fantasma)."""
        inicio, _ = granularidad.rango_minuto(numero)
        return [e for minuto in self.minutos[:numero] for e in minuto if e.fin > inicio]

    # --- Shorts ----------------------------------------------------------------

    def agregar_short(self, short: Short) -> None:
        if short.id in self.shorts:
            raise ErrorModelo(f"Ya existe un Short {short.id}.")
        self.shorts[short.id] = short

    def quitar_short(self, id_short: str) -> Short:
        try:
            return self.shorts.pop(id_short)
        except KeyError:
            raise NoEncontrado(f"No hay un Short {id_short} en {self.codigo}.") from None

    def shorts_que_cruzan(self, numero_minuto: int) -> list[Short]:
        return [s for s in self.shorts.values() if numero_minuto in s.minutos_cruzados]

    # --- Renders ---------------------------------------------------------------

    def siguiente_version(self, desde: int | None, hasta: int | None) -> int:
        """Versión siguiente para un entregable con ese alcance."""
        versiones = [
            r.nombre.version for r in self.renders
            if r.nombre.desde == desde and r.nombre.hasta == hasta
        ]
        return max(versiones, default=0) + 1
