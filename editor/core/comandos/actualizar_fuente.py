"""Actualizar las copias de una Pieza después de volver a hornearla.

Cada Elemento que es copia de la Pieza toma la versión nueva, su duración de
fuente y sus datos de medio. Si las asas de inicio cambiaron, `fuente_entrada`
se corrige para que siga viéndose el mismo tramo. El archivo materializado se
reemplaza en el siguiente guardado (la versión distinta lo delata).

Las copias pueden estar en capítulos no cargados: quien llama (el servicio de
horneado) indica qué capítulos tocar, según las copias de `_pieza.json`.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo
from editor.core.comandos.compuesto import ComandoCompuesto
from editor.core.modelo.capa import TipoCapa
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import TipoFuente
from editor.core.modelo.pieza import Pieza
from editor.core.modelo.proyecto import Proyecto


class ActualizarFuenteEnCapitulo(EdicionCapitulo):
    descripcion = "Actualizar Pieza"

    def __init__(self, capitulo: int, pieza: Pieza, asas_inicio_anteriores: int) -> None:
        super().__init__(capitulo)
        if pieza.horneado is None:
            raise ValueError("La Pieza no está horneada.")
        self.id_pieza = pieza.id
        self.horneado = pieza.horneado
        self.desplazamiento = pieza.horneado.asas_inicio - asas_inicio_anteriores

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {
            e.id for e in capitulo.todos_los_elementos()
            if e.fuente.tipo is TipoFuente.PIEZA and e.fuente.ref == self.id_pieza
        }

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        horneado = self.horneado
        for identificador in self.involucrados(capitulo):
            elemento = capitulo.obtener(identificador)
            es_audio = elemento.capa.tipo is TipoCapa.AUDIO
            elemento.fuente = type(elemento.fuente)(TipoFuente.PIEZA, self.id_pieza, horneado.version)
            elemento.tiempo.fuente_duracion = horneado.fotogramas
            elemento.tiempo.fuente_entrada = max(0, elemento.tiempo.fuente_entrada + self.desplazamiento)
            elemento.tiene_audio = horneado.tiene_audio
            if not es_audio:
                elemento.extension = horneado.extension
                elemento.ancho = horneado.ancho
                elemento.alto = horneado.alto
                elemento.tiene_alfa = horneado.tiene_alfa
        return set()


def actualizar_fuente(pieza: Pieza, asas_inicio_anteriores: int, capitulos: list[int]) -> ComandoCompuesto:
    return ComandoCompuesto(
        f"Actualizar copias de {pieza.nombre}",
        [ActualizarFuenteEnCapitulo(numero, pieza, asas_inicio_anteriores) for numero in sorted(set(capitulos))],
    )
