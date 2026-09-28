"""Miniaturas y formas de onda para dibujar dentro de los Elementos de la timeline.

Lee lo que ya generan los servicios (`miniaturas.ruta_tira`, `forma_onda.ruta_onda`) y
lo guarda en memoria. Si falta, pide generarlo una sola vez por archivo; al terminar,
la timeline se redibuja.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PIL import Image

from editor.app.controladores import taller as ctl_taller
from editor.core.servicios import banco, forma_onda, miniaturas

if TYPE_CHECKING:
    from editor.app.estado import Sesion

MAXIMO_EN_MEMORIA = 200


class ProveedorMedios:
    def __init__(self, sesion: "Sesion", al_generar: Callable[[], None]) -> None:
        self.sesion = sesion
        self._al_generar = al_generar
        self._tiras: dict[Path, tuple[Image.Image, int] | None] = {}   # imagen, cantidad de cuadros
        self._recortes: dict[tuple[Path, int, int], bytes] = {}
        self._ondas: dict[Path, list[list[float]] | None] = {}
        self._pedidos: set[Path] = set()

    @property
    def raiz(self) -> Path:
        assert self.sesion.proyecto.raiz is not None
        return self.sesion.proyecto.raiz

    def olvidar(self) -> None:
        self._tiras.clear()
        self._recortes.clear()
        self._ondas.clear()
        self._pedidos.clear()

    def _pedir(self, ruta: Path) -> None:
        if ruta in self._pedidos or not ruta.exists():
            return
        self._pedidos.add(ruta)

        def listo() -> None:
            self._tiras.pop(ruta, None)
            self._ondas.pop(ruta, None)
            self._al_generar()

        ctl_taller.preparar_vista_previa(self.sesion, ruta, listo)

    # --- Miniaturas ------------------------------------------------------------------------

    def _tira(self, ruta: Path) -> tuple[Image.Image, int] | None:
        if ruta not in self._tiras:
            archivo = miniaturas.ruta_tira(self.raiz, ruta)
            if not archivo.exists():
                if not banco.existe(self.raiz, ruta):
                    self._pedir(ruta)
                return None
            with Image.open(archivo) as imagen:
                tira = imagen.convert("RGB")
            self._tiras[ruta] = (tira, max(1, tira.width // miniaturas.ANCHO))
        return self._tiras[ruta]

    def miniatura(self, ruta: Path, fraccion: float, alto: int) -> bytes | None:
        """JPEG de la miniatura en la posición `fraccion` (0–1) del archivo, a `alto` px."""
        tira = self._tira(ruta)
        if tira is None:
            return None
        imagen, cantidad = tira
        indice = max(0, min(cantidad - 1, int(fraccion * cantidad)))
        clave = (ruta, indice, alto)
        if clave not in self._recortes:
            if len(self._recortes) > MAXIMO_EN_MEMORIA:
                self._recortes.clear()
            recorte = imagen.crop((indice * miniaturas.ANCHO, 0, (indice + 1) * miniaturas.ANCHO, miniaturas.ALTO))
            recorte = recorte.resize((max(1, round(alto * miniaturas.ANCHO / miniaturas.ALTO)), max(1, alto)))
            salida = BytesIO()
            recorte.save(salida, format="JPEG", quality=70)
            self._recortes[clave] = salida.getvalue()
        return self._recortes[clave]

    def imagen_fija(self, ruta: Path, alto: int) -> bytes | None:
        """Miniatura de una imagen (Bruto de imagen colocado directamente)."""
        clave = (ruta, -1, alto)
        if clave not in self._recortes:
            try:
                with Image.open(ruta) as imagen:
                    imagen = imagen.convert("RGB")
                    imagen.thumbnail((alto * 4, alto))
                    salida = BytesIO()
                    imagen.save(salida, format="JPEG", quality=70)
            except OSError:
                return None
            self._recortes[clave] = salida.getvalue()
        return self._recortes[clave]

    # --- Forma de onda ---------------------------------------------------------------------

    def onda(self, ruta: Path) -> list[list[float]] | None:
        """Picos por fotograma (24 fps) y canal, 0–1; None si todavía no está."""
        if ruta not in self._ondas:
            archivo = forma_onda.ruta_onda(self.raiz, ruta)
            if not archivo.exists():
                self._pedir(ruta)
                return None
            try:
                self._ondas[ruta] = json.loads(archivo.read_text(encoding="utf-8"))["picos"]
            except (OSError, ValueError, KeyError):
                self._ondas[ruta] = None
        return self._ondas[ruta]
