"""Operaciones de rango: cerrar huecos, levantar y extraer, congelar fotograma."""

from __future__ import annotations

import copy

from editor.core.comandos.agregar_elemento import colocar_con_modo
from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.comandos.operaciones import (
    ModoColocacion,
    abrir_hueco,
    desplazar,
    elementos_en_capa,
)
from editor.core.espacio.transform import PROPIEDADES_ANIMABLES
from editor.core.modelo.capa import Capa, TipoCapa
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.keyframe import Animacion
from editor.core.modelo.proyecto import Proyecto
from editor.core.tiempo import granularidad


class CerrarHuecos(EdicionCapitulo):
    """Compacta un minuto: en cada capa, cada Elemento empieza donde termina el anterior.

    El primero de cada capa conserva su posición. No se cruza de minuto.
    """

    descripcion = "Cerrar huecos"

    def __init__(self, capitulo: int, minuto: int, capa: Capa | None = None) -> None:
        super().__init__(capitulo)
        granularidad.validar_minuto(minuto)
        self.minuto = minuto
        self.capa = capa

    def _objetivo(self, capitulo: Capitulo) -> list:
        return [e for e in capitulo.minuto(self.minuto) if self.capa is None or e.capa == self.capa]

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {e.id for e in self._objetivo(capitulo)}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        objetivo = [self.obtener(capitulo, e.id) for e in self._objetivo(capitulo)]
        self.retirar(capitulo, objetivo)
        por_capa: dict[str, list] = {}
        for elemento in objetivo:
            por_capa.setdefault(elemento.capa.codigo, []).append(elemento)
        for elementos in por_capa.values():
            elementos.sort(key=lambda e: e.inicio)
            for anterior, siguiente in zip(elementos, elementos[1:]):
                solape = siguiente.transicion_entrada.duracion if siguiente.transicion_entrada else 0
                siguiente.tiempo.inicio = anterior.fin - solape
        self.colocar(capitulo, objetivo)
        return set()


class QuitarRango(EdicionCapitulo):
    """Levantar (deja hueco) o extraer (cierra el hueco) el rango [inicio, fin) en unas capas.

    Extraer corre hacia la izquierda lo que viene después en esas capas, dentro
    del minuto del inicio del rango.
    """

    def __init__(self, capitulo: int, inicio: int, fin: int, capas: list[Capa], extraer: bool) -> None:
        super().__init__(capitulo)
        if fin <= inicio:
            raise ValueError("El rango está vacío.")
        self.inicio = inicio
        self.fin = fin
        self.capas = list(capas)
        self.extraer = extraer
        self.descripcion = "Extraer rango" if extraer else "Levantar rango"

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        ids = set()
        for capa in self.capas:
            for elemento in elementos_en_capa(capitulo, capa, False):
                if elemento.fin > self.inicio:
                    ids.add(elemento.id)
        return ids

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        creados: set[str] = set()
        minuto = granularidad.minuto_de(self.inicio)
        for capa in self.capas:
            modificados, _, partidos = abrir_hueco(
                capitulo, capa, False, self.inicio, self.fin, lambda: self.ids.nuevo(proyecto)
            )
            creados |= {e.id for e in partidos}
            pendientes = modificados + partidos
            if self.extraer:
                despues = [e for e in pendientes if e.inicio >= self.fin]
                despues += [
                    self.obtener(capitulo, e.id) for e in elementos_en_capa(capitulo, capa, False)
                    if e.inicio >= self.fin and e.minuto_inicio == minuto
                ]
                self.retirar(capitulo, despues)
                desplazar(despues, -(self.fin - self.inicio))
                ids_despues = {e.id for e in despues}
                pendientes = [e for e in pendientes if e.id not in ids_despues] + despues
            self.colocar(capitulo, pendientes)
        return creados


class CongelarFotograma(EdicionCapitulo):
    """Crea un Elemento que muestra fijo el fotograma `f` de otro.

    Usa la misma fuente; la transformación evaluada en `f` queda como estática.
    """

    descripcion = "Congelar fotograma"

    def __init__(
        self,
        capitulo: int,
        id_elemento: str,
        f: int,
        inicio: int,
        duracion: int,
        capa: Capa | None = None,
        modo: ModoColocacion = ModoColocacion.RECHAZAR,
    ) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.f = f
        self.inicio = inicio
        self.duracion = duracion
        self.capa = capa
        self.modo = modo

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        origen = capitulo.buscar(self.id_elemento)
        if origen is None or self.modo is ModoColocacion.RECHAZAR:
            return set()
        capa = self.capa or origen.capa
        return {e.id for e in elementos_en_capa(capitulo, capa, origen.en_global)
                if e.inicio < self.inicio + self.duracion and self.inicio < e.fin} | \
            ({e.id for e in capitulo.todos_los_elementos() if e.fin > self.inicio}
             if self.modo is ModoColocacion.INSERTAR else set())

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        origen = capitulo.obtener(self.id_elemento)
        if origen.capa.tipo is not TipoCapa.VIDEO or not origen.contiene(self.f):
            raise EdicionRechazada("Se congela un fotograma dentro de un Elemento de video.")
        congelado = copy.deepcopy(origen)
        congelado.id = self.ids.nuevo(proyecto)
        congelado.archivo = None
        congelado.capa = self.capa or origen.capa
        congelado.espacio = origen.transform_en(self.f)
        congelado.animacion = Animacion({
            clave: pista for clave, pista in origen.animacion.pistas.items() if clave not in PROPIEDADES_ANIMABLES
        })
        congelado.transicion_entrada = None
        congelado.audio.silenciado = True
        congelado.tiempo.fuente_entrada = origen.fotograma_fuente(self.f)
        congelado.tiempo.inicio = self.inicio
        congelado.tiempo.duracion = self.duracion
        congelado.tiempo.velocidad = 1.0
        congelado.tiempo.congelado = True
        creados = colocar_con_modo(self, proyecto, capitulo, [congelado], self.modo)
        return creados | {congelado.id}
