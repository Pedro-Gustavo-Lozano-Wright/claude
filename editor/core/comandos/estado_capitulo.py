"""Base para comandos sobre el estado del capítulo que no son Elementos.

Capas, marcadores, Shorts, título y estado de los minutos: se guarda una copia
de esa parte antes de cambiarla y deshacer la restaura.
"""

from __future__ import annotations

import copy
from abc import abstractmethod
from typing import Any

from editor.core.comandos.comando import Afectados, Comando
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class EdicionEstadoCapitulo(Comando):
    #: Atributos del Capitulo que el comando puede cambiar.
    partes: tuple[str, ...] = ()

    def __init__(self, capitulo: int) -> None:
        self.capitulo = capitulo
        self._antes: dict[str, Any] = {}
        self._minutos_antes: list[tuple[bool, str]] = []
        self._afectados = Afectados(capitulo, estado_capitulo=True)

    @abstractmethod
    def aplicar(self, capitulo: Capitulo) -> Afectados:
        """Hace el cambio y devuelve qué afectó (minutos, shorts…)."""

    def ejecutar(self, proyecto: Proyecto) -> None:
        capitulo = proyecto.capitulo(self.capitulo)
        self._antes = {parte: copy.deepcopy(getattr(capitulo, parte)) for parte in self.partes}
        self._minutos_antes = [(m.listo, m.notas) for m in capitulo.minutos]
        try:
            self._afectados = self.aplicar(capitulo)
        except Exception:
            self._restaurar(capitulo)
            raise

    def deshacer(self, proyecto: Proyecto) -> None:
        self._restaurar(proyecto.capitulo(self.capitulo))

    def _restaurar(self, capitulo: Capitulo) -> None:
        for parte, valor in self._antes.items():
            setattr(capitulo, parte, copy.deepcopy(valor))
        for minuto, (listo, notas) in zip(capitulo.minutos, self._minutos_antes):
            minuto.listo, minuto.notas = listo, notas

    def afectados(self) -> list[Afectados]:
        return [self._afectados]

    def clave_fusion(self) -> tuple | None:
        """Como en `EdicionCapitulo`: pasos de un mismo gesto con valores absolutos."""
        return None

    def fusionar(self, siguiente: Comando) -> bool:
        clave = self.clave_fusion()
        if clave is None or type(siguiente) is not type(self):
            return False
        assert isinstance(siguiente, EdicionEstadoCapitulo)
        if siguiente.clave_fusion() != clave:
            return False
        antes, minutos_antes = self._antes, self._minutos_antes
        self.__dict__.update({k: v for k, v in siguiente.__dict__.items() if k not in ("_antes", "_minutos_antes")})
        self._antes, self._minutos_antes = antes, minutos_antes
        return True
