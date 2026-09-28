"""Piezas pequeñas de interfaz compartidas por los paneles."""

from __future__ import annotations


def actualizar(*controles) -> None:
    """`update()` que no falla si el control no está en la página (panel oculto en este espacio)."""
    for control in controles:
        try:
            control.update()
        except RuntimeError:   # Flet: "Control must be added to the page first"
            pass

