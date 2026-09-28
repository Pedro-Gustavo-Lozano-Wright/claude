"""Imagen de relleno mientras llega la primera vista previa."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO


@lru_cache(maxsize=1)
def imagen_vacia() -> bytes:
    from PIL import Image

    salida = BytesIO()
    Image.new("RGB", (16, 9)).save(salida, format="PNG")
    return salida.getvalue()
