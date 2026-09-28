"""Global: pistas que abarcan el capítulo completo (música, narración, títulos).

Vive en `capNNNN/global/`. Sus capas son un espacio aparte de las de los
minutos: A1 de Global no choca con A1 de un minuto.
"""

from __future__ import annotations

from dataclasses import dataclass

from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO
from editor.core.modelo.composicion import Composicion
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.errores import ErrorModelo


@dataclass
class Global(Composicion):
    @classmethod
    def nuevo(cls) -> "Global":
        return cls(inicio=0, duracion=FOTOGRAMAS_POR_CAPITULO)

    def validar_ubicacion(self, elemento: Elemento) -> None:
        if not elemento.en_global:
            raise ErrorModelo(f"El Elemento {elemento.id} no está marcado como Global.")
        if not 0 <= elemento.inicio < FOTOGRAMAS_POR_CAPITULO:
            raise ErrorModelo(f"El Elemento {elemento.id} empieza fuera del capítulo.")
