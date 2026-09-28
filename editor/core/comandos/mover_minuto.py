"""Intercambiar el contenido de dos minutos completos.

Todo lo que empieza en un minuto pasa al otro conservando su posición dentro
del minuto. Implica renombrar y mover sus archivos al guardar: la interfaz
debe confirmarlo antes.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo
from editor.core.estandar import FOTOGRAMAS_POR_MINUTO
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class IntercambiarMinutos(EdicionCapitulo):
    descripcion = "Intercambiar minutos"

    def __init__(self, capitulo: int, minuto_a: int, minuto_b: int) -> None:
        super().__init__(capitulo)
        if minuto_a == minuto_b:
            raise ValueError("Los minutos deben ser distintos.")
        self.minuto_a = minuto_a
        self.minuto_b = minuto_b

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {e.id for e in capitulo.minuto(self.minuto_a)} | {e.id for e in capitulo.minuto(self.minuto_b)}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        de_a = [self.obtener(capitulo, e.id) for e in list(capitulo.minuto(self.minuto_a))]
        de_b = [self.obtener(capitulo, e.id) for e in list(capitulo.minuto(self.minuto_b))]
        self.retirar(capitulo, de_a + de_b)
        salto = (self.minuto_b - self.minuto_a) * FOTOGRAMAS_POR_MINUTO
        for elemento in de_a:
            elemento.tiempo.inicio += salto
        for elemento in de_b:
            elemento.tiempo.inicio -= salto
        self.colocar(capitulo, de_a + de_b)
        a, b = capitulo.minuto(self.minuto_a), capitulo.minuto(self.minuto_b)
        a.listo, b.listo = b.listo, a.listo
        a.notas, b.notas = b.notas, a.notas
        return set()

    def deshacer(self, proyecto: Proyecto) -> None:
        super().deshacer(proyecto)
        capitulo = proyecto.capitulo(self.capitulo)
        a, b = capitulo.minuto(self.minuto_a), capitulo.minuto(self.minuto_b)
        a.listo, b.listo = b.listo, a.listo
        a.notas, b.notas = b.notas, a.notas
