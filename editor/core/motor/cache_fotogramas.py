"""Caché LRU de fotogramas decodificados con límite en MB."""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Hashable

import numpy as np


class CacheFotogramas:
    def __init__(self, limite_mb: int = 512) -> None:
        self.limite = max(1, limite_mb) * 1024 * 1024
        self._datos: OrderedDict[Hashable, np.ndarray] = OrderedDict()
        self._usado = 0
        self._candado = threading.Lock()

    def obtener(self, clave: Hashable) -> np.ndarray | None:
        with self._candado:
            imagen = self._datos.get(clave)
            if imagen is not None:
                self._datos.move_to_end(clave)
            return imagen

    def guardar(self, clave: Hashable, imagen: np.ndarray) -> None:
        with self._candado:
            anterior = self._datos.pop(clave, None)
            if anterior is not None:
                self._usado -= anterior.nbytes
            self._datos[clave] = imagen
            self._usado += imagen.nbytes
            while self._usado > self.limite and self._datos:
                _, viejo = self._datos.popitem(last=False)
                self._usado -= viejo.nbytes

    def olvidar(self, ruta: Path | None = None) -> None:
        """Descarta todo (o lo de una ruta: la clave empieza por la ruta)."""
        with self._candado:
            if ruta is None:
                self._datos.clear()
                self._usado = 0
                return
            for clave in [c for c in self._datos if isinstance(c, tuple) and c and c[0] == ruta]:
                self._usado -= self._datos.pop(clave).nbytes

    @property
    def usado_mb(self) -> float:
        return self._usado / (1024 * 1024)
