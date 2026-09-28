"""Tira de miniaturas para dibujar un clip en la timeline.

Se arma con imágenes del banco: una por segundo (hasta 60), a 96×54.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from editor.core.servicios.banco import INDICE, carpeta_banco

ANCHO, ALTO = 96, 54
MAXIMO = 60


def ruta_tira(raiz: Path, ruta: Path) -> Path:
    return carpeta_banco(raiz, ruta) / "tira.jpg"


def generar(raiz: Path, ruta: Path) -> Path | None:
    """Requiere el banco. Devuelve la ruta de la tira (horizontal) o None si no hay banco."""
    carpeta = carpeta_banco(raiz, ruta)
    if not (carpeta / INDICE).exists():
        return None
    destino = carpeta / "tira.jpg"
    if destino.exists():
        return destino
    datos = json.loads((carpeta / INDICE).read_text(encoding="utf-8"))
    total, fps_banco, formato = int(datos["fotogramas"]), int(datos["fps_banco"]), datos["formato"]
    cantidad = max(1, min(MAXIMO, total // fps_banco or 1))
    tira = Image.new("RGB", (ANCHO * cantidad, ALTO))
    for i in range(cantidad):
        k = min(total - 1, round(i * total / cantidad))
        with Image.open(carpeta / f"f{k:06d}.{formato}") as imagen:
            imagen = imagen.convert("RGB")
            imagen.thumbnail((ANCHO, ALTO))
            tira.paste(imagen, (i * ANCHO + (ANCHO - imagen.width) // 2, (ALTO - imagen.height) // 2))
    tira.save(destino, quality=80)
    return destino
