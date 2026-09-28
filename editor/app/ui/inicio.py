"""Pantalla de inicio: crear, abrir y proyectos recientes (T12.5)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from editor.app.controladores import proyecto as ctl_proyecto
from editor.app.ui.tema import TEMA, texto, texto_suave
from editor.core.tiempo.nomenclatura import normalizar_nombre

if TYPE_CHECKING:
    from editor.app.aplicacion import Aplicacion


class Inicio:
    def __init__(self, raiz: "Aplicacion") -> None:
        self.raiz = raiz
        recientes = ctl_proyecto.recientes(raiz.ajustes)
        filas: list[ft.Control] = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.MOVIE, color=TEMA.acento),
                title=texto(ruta.name),
                subtitle=texto_suave(str(ruta.parent)),
                on_click=lambda _, r=ruta: raiz.abrir(r),
            )
            for ruta in recientes
        ] or [texto_suave("Todavía no hay proyectos recientes.")]
        self.control = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Editor por capítulos", size=28, weight=ft.FontWeight.BOLD, color=TEMA.texto),
                    texto_suave("Capítulos de 24 minutos · minutos de 60 s · 24 fps · 1280×720"),
                    ft.Row([
                        ft.FilledButton("Nuevo proyecto", icon=ft.Icons.CREATE_NEW_FOLDER, on_click=self._nuevo),
                        ft.OutlinedButton("Abrir proyecto", icon=ft.Icons.FOLDER_OPEN, on_click=self._abrir),
                    ]),
                    ft.Divider(),
                    texto_suave("RECIENTES"),
                    ft.Column(filas, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True),
                ],
                spacing=12,
                width=640,
                expand=True,
            ),
            alignment=ft.Alignment.TOP_CENTER,
            padding=40,
            bgcolor=TEMA.fondo,
            expand=True,
        )

    async def _abrir(self, _evento) -> None:
        carpeta = await self.raiz.selector.get_directory_path(dialog_title="Carpeta del proyecto")
        if carpeta:
            self.raiz.abrir(Path(carpeta))

    async def _nuevo(self, _evento) -> None:
        carpeta = await self.raiz.selector.get_directory_path(dialog_title="Carpeta donde crear el proyecto")
        if not carpeta:
            return
        nombre = ft.TextField(label="Nombre del proyecto", autofocus=True, hint_text="mi-serie")

        def crear() -> None:
            valor = normalizar_nombre(nombre.value or "")
            if not valor:
                self.raiz.avisar("Escriba un nombre para el proyecto.")
                return
            self.raiz.crear(Path(carpeta) / valor)

        self.raiz.dialogo("Nuevo proyecto", nombre, [("Crear", crear), ("Cancelar", None)])
