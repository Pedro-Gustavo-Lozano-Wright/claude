"""Barra arrastrable que redimensiona paneles vecinos.

El divisor no conoce los paneles: informa el desplazamiento en píxeles y quien
lo usa ajusta los tamaños. Doble clic pliega o despliega el panel.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from editor.app.ui.tema import TEMA

GROSOR = 5


class Divisor:
    def __init__(
        self,
        vertical: bool,
        al_mover: Callable[[float], None],
        al_soltar: Callable[[], None] | None = None,
        al_plegar: Callable[[], None] | None = None,
    ) -> None:
        """`vertical=True` separa columnas (se arrastra en x); False separa filas (en y)."""
        self._vertical = vertical
        self._al_mover = al_mover
        self._al_soltar = al_soltar
        self._al_plegar = al_plegar
        barra = ft.Container(bgcolor=TEMA.borde, width=GROSOR if vertical else None,
                             height=None if vertical else GROSOR)
        self.control = ft.GestureDetector(
            content=barra,
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN if vertical else ft.MouseCursor.RESIZE_ROW,
            drag_interval=16,
            on_pan_update=self._mover,
            on_pan_end=self._soltar,
            on_double_tap=self._plegar,
        )

    def _mover(self, evento: ft.DragUpdateEvent) -> None:
        if evento.local_delta is None:
            return
        self._al_mover(evento.local_delta.x if self._vertical else evento.local_delta.y)

    def _soltar(self, _evento) -> None:
        if self._al_soltar:
            self._al_soltar()

    def _plegar(self, _evento) -> None:
        if self._al_plegar:
            self._al_plegar()
