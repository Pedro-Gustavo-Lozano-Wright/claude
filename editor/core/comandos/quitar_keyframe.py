"""Quitar keyframes."""

from __future__ import annotations

from editor.core.comandos.agregar_keyframe import animacion_de
from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class QuitarKeyframe(EdicionCapitulo):
    descripcion = "Quitar keyframe"

    def __init__(self, capitulo: int, id_elemento: str, propiedad: str, f: int,
                 indice_efecto: int | None = None) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.propiedad = propiedad
        self.f = f
        self.indice_efecto = indice_efecto

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        animacion = animacion_de(elemento, self.propiedad, self.indice_efecto)
        if animacion.pista(self.propiedad).quitar(self.f) is None:
            raise EdicionRechazada(f"No hay keyframe en el fotograma {self.f}.")
        animacion.limpiar_vacias()
        return set()
