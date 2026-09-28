"""Código de tiempo del capítulo: MM:SS.FF (minuto, segundo, fotograma a 24 fps)."""

from __future__ import annotations

import re

from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO
from editor.core.tiempo.granularidad import componer, descomponer

_PATRON = re.compile(r"\s*(\d{1,2}):(\d{1,2})(?:[.:](\d{1,2}))?\s*")


def formatear(f: int) -> str:
    minuto, segundo, fotograma = descomponer(max(0, f))
    return f"{minuto:02d}:{segundo:02d}.{fotograma:02d}"


def interpretar(texto: str) -> int | None:
    """'02:12.08' o '2:12' → fotograma del capítulo; None si no es válido."""
    coincidencia = _PATRON.fullmatch(texto)
    if coincidencia is None:
        return None
    minuto, segundo, fotograma = (int(g) if g else 0 for g in coincidencia.groups())
    try:
        f = componer(minuto, segundo, fotograma)
    except ValueError:
        return None
    return f if 0 <= f < FOTOGRAMAS_POR_CAPITULO else None


def duracion(fotogramas: int) -> str:
    """Duración corta para etiquetas: '5s00', '1m02s12'."""
    minuto, segundo, fotograma = descomponer(max(0, fotogramas))
    return f"{minuto}m{segundo:02d}s{fotograma:02d}" if minuto else f"{segundo}s{fotograma:02d}"
