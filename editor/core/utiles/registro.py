"""Configuración del registro (logging) de la aplicación."""

from __future__ import annotations

import logging
from pathlib import Path

FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
FORMATO_FECHA = "%H:%M:%S"


def configurar_registro(nivel: str = "INFO", archivo: Path | None = None) -> None:
    manejadores: list[logging.Handler] = [logging.StreamHandler()]
    if archivo is not None:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        manejadores.append(logging.FileHandler(archivo, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, nivel.upper(), logging.INFO),
        format=FORMATO,
        datefmt=FORMATO_FECHA,
        handlers=manejadores,
        force=True,
    )


def obtener_registro(nombre: str) -> logging.Logger:
    return logging.getLogger(nombre)
