"""Tokens de color y tipografía (PROJECT.md 22.3).

Se leen de `recursos/temas/<nombre>.json`; si falta un token se usa el valor
por defecto del tema oscuro, así un tema incompleto nunca rompe la interfaz.
"""

from __future__ import annotations

import json
from pathlib import Path

import flet as ft

CARPETA_TEMAS = Path(__file__).parent / "recursos" / "temas"


class Tema:
    def __init__(self, nombre: str = "oscuro") -> None:
        base = json.loads((CARPETA_TEMAS / "oscuro.json").read_text(encoding="utf-8"))
        ruta = CARPETA_TEMAS / f"{nombre}.json"
        if nombre != "oscuro" and ruta.exists():
            base.update(json.loads(ruta.read_text(encoding="utf-8")))
        self._valores: dict[str, object] = base

    def __getattr__(self, token: str) -> str:
        try:
            return self._valores[token]  # type: ignore[return-value]
        except KeyError:
            raise AttributeError(f"Token de tema desconocido: {token}") from None

    def color_capa(self, tipo: str) -> str:
        return {"V": self.capa_video, "A": self.capa_audio, "T": self.capa_texto}[tipo]

    def aplicar(self, page: ft.Page) -> None:
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = self.fondo
        page.dark_theme = ft.Theme(
            color_scheme_seed=self.acento,
            font_family=self.fuente,
        )


TEMA = Tema()


def texto(valor: str, tamano: float | None = None, color: str | None = None, **opciones) -> ft.Text:
    return ft.Text(valor, size=tamano or TEMA.tamano_texto, color=color or TEMA.texto, **opciones)


def texto_suave(valor: str, **opciones) -> ft.Text:
    return ft.Text(valor, size=TEMA.tamano_pequeno, color=TEMA.texto_suave, **opciones)


def panel(contenido: ft.Control, **opciones) -> ft.Container:
    """Contenedor estándar de una sección."""
    opciones.setdefault("bgcolor", TEMA.panel)
    opciones.setdefault("padding", 6)
    return ft.Container(content=contenido, **opciones)


def titulo_panel(valor: str, *acciones: ft.Control) -> ft.Row:
    return ft.Row(
        [ft.Text(valor.upper(), size=TEMA.tamano_pequeno, color=TEMA.texto_suave, weight=ft.FontWeight.BOLD),
         ft.Row(list(acciones), spacing=0)],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        height=28,
    )
