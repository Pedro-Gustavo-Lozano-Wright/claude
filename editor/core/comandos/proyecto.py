"""Ediciones del proyecto entero: idiomas.

Los idiomas del proyecto son las pistas de audio del render ("spa", "eng"…).
El primero es el idioma principal. Quitar un idioma que todavía usa alguna capa A
se rechaza: la capa quedaría sonando en un idioma que ya no existe.
"""

from __future__ import annotations

import re

from editor.core.comandos.comando import Afectados, Comando, EdicionRechazada
from editor.core.modelo.proyecto import Proyecto

_CODIGO = re.compile(r"^[a-z]{2,3}$")


class CambiarIdiomas(Comando):
    descripcion = "Cambiar idiomas del proyecto"

    def __init__(self, idiomas: list[str], en_uso_fuera: set[str] | frozenset[str] = frozenset()) -> None:
        """`en_uso_fuera`: idiomas que usan capítulos no cargados (`proyecto_fs.consultas.idiomas_en_disco`)."""
        limpios = [i.strip().lower() for i in idiomas]
        if not limpios:
            raise ValueError("El proyecto necesita al menos un idioma.")
        invalidos = [i for i in limpios if not _CODIGO.match(i)]
        if invalidos:
            raise ValueError(f"Código de idioma inválido (ISO 639-1, p. ej. es, en): {', '.join(invalidos)}")
        if len(set(limpios)) != len(limpios):
            raise ValueError("Hay idiomas repetidos.")
        self.idiomas = limpios
        self.en_uso_fuera = set(en_uso_fuera)
        self._antes: list[str] | None = None

    def ejecutar(self, proyecto: Proyecto) -> None:
        quitados = set(proyecto.idiomas) - set(self.idiomas)
        if quitados:
            en_uso = (idiomas_en_uso(proyecto) | self.en_uso_fuera) & quitados
            if en_uso:
                raise EdicionRechazada(
                    f"El idioma {', '.join(sorted(en_uso))} está asignado a capas de audio; cámbielas primero.")
        self._antes = list(proyecto.idiomas)
        proyecto.idiomas = list(self.idiomas)

    def deshacer(self, proyecto: Proyecto) -> None:
        if self._antes is not None:
            proyecto.idiomas = list(self._antes)

    def afectados(self) -> list[Afectados]:
        return [Afectados()]


def idiomas_en_uso(proyecto: Proyecto) -> set[str]:
    """Idiomas asignados a capas A en los capítulos cargados."""
    usados: set[str] = set()
    for capitulo in proyecto.capitulos_cargados():
        usados |= {estado.idioma for estado in capitulo.capas.values() if estado.idioma}
    return usados
