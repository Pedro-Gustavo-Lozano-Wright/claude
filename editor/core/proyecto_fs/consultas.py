"""Consultas rápidas sobre capítulos **no cargados** (lee JSON del disco, no arma el modelo).

Solo hay un capítulo en memoria a la vez (el que se edita). Para saber si algo de
otro capítulo depende de un Bruto o de un idioma, se leen sus gemelos y su
`_capitulo.json`: los capítulos no cargados siempre están guardados, así que el
disco dice la verdad.
"""

from __future__ import annotations

import json
from pathlib import Path

from editor.core.tiempo import nomenclatura as nom


def _capitulos_en_disco(raiz: Path, excluir: set[int]) -> list[Path]:
    carpetas = []
    for carpeta in sorted(raiz.glob("cap[0-9][0-9][0-9][0-9]*")):
        try:
            numero = int(carpeta.name[3:7])
        except ValueError:
            continue
        if carpeta.is_dir() and numero not in excluir:
            carpetas.append(carpeta)
    return carpetas


def fuentes_en_disco(raiz: Path, excluir: set[int]) -> set[str]:
    """IDs de Brutos y Piezas que usan los Elementos de los capítulos no excluidos."""
    refs: set[str] = set()
    for carpeta in _capitulos_en_disco(raiz, excluir):
        for gemelo in carpeta.glob("*/*.json"):
            if gemelo.name.startswith("_"):
                continue
            try:
                ref = json.loads(gemelo.read_text(encoding="utf-8")).get("fuente", {}).get("ref")
            except (OSError, ValueError, AttributeError):
                continue
            if ref:
                refs.add(ref)
    return refs


def idiomas_en_disco(raiz: Path, excluir: set[int]) -> set[str]:
    """Idiomas asignados a capas A en los capítulos no excluidos."""
    idiomas: set[str] = set()
    for carpeta in _capitulos_en_disco(raiz, excluir):
        try:
            capas = json.loads((carpeta / nom.ARCHIVO_CAPITULO).read_text(encoding="utf-8")).get("capas", {})
        except (OSError, ValueError, AttributeError):
            continue
        idiomas |= {estado.get("idioma") for estado in capas.values() if isinstance(estado, dict) and estado.get("idioma")}
    return idiomas
