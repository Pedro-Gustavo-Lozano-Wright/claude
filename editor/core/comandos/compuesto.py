"""Comando compuesto: varios comandos como un solo paso de deshacer (T6.3).

Si uno falla, los ya ejecutados se deshacen en orden inverso y el modelo
queda como estaba.
"""

from __future__ import annotations

from editor.core.comandos.comando import Afectados, Comando
from editor.core.modelo.proyecto import Proyecto


class ComandoCompuesto(Comando):
    def __init__(self, descripcion: str, comandos: list[Comando]) -> None:
        self.descripcion = descripcion
        self.comandos = list(comandos)

    def ejecutar(self, proyecto: Proyecto) -> None:
        hechos: list[Comando] = []
        try:
            for comando in self.comandos:
                comando.ejecutar(proyecto)
                hechos.append(comando)
        except Exception:
            for comando in reversed(hechos):
                comando.deshacer(proyecto)
            raise

    def deshacer(self, proyecto: Proyecto) -> None:
        for comando in reversed(self.comandos):
            comando.deshacer(proyecto)

    def afectados(self) -> list[Afectados]:
        por_capitulo: dict[int | None, Afectados] = {}
        for comando in self.comandos:
            for afectado in comando.afectados():
                clave = afectado.capitulo
                por_capitulo[clave] = por_capitulo[clave].unir(afectado) if clave in por_capitulo else afectado
        return list(por_capitulo.values())
