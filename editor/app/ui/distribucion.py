"""Espacios de trabajo: tamaños y paneles visibles (PROJECT.md 16.2).

Los valores por defecto están en `config/distribucion.json`; los cambios del
usuario se guardan en `~/.config/editor/distribucion.json`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from editor.core.ajustes import (
    ARCHIVO_DISTRIBUCION,
    CONFIG_REPOSITORIO,
    CONFIG_USUARIO,
    escribir_json,
    leer_json,
)

PANELES = ("navegador", "monitor", "inspector", "mapa", "timeline", "cola_render")
MINIMOS = {"navegador": 160, "inspector": 220, "mapa": 36, "timeline": 140}
MAXIMOS = {"navegador": 520, "inspector": 560, "mapa": 160, "timeline": 900}


@dataclass
class Espacio:
    nombre: str
    tamanos: dict[str, float]
    visibles: list[str]
    plegados: set[str] = field(default_factory=set)

    def visible(self, panel: str) -> bool:
        return panel in self.visibles and panel not in self.plegados

    def tamano(self, panel: str) -> float:
        return self.tamanos.get(panel, MINIMOS.get(panel, 200))

    def ajustar(self, panel: str, delta: float) -> None:
        nuevo = self.tamano(panel) + delta
        self.tamanos[panel] = max(MINIMOS.get(panel, 0), min(MAXIMOS.get(panel, 2000), nuevo))

    def alternar_plegado(self, panel: str) -> None:
        self.plegados.symmetric_difference_update({panel})


class Distribucion:
    def __init__(self) -> None:
        self._por_defecto = leer_json(CONFIG_REPOSITORIO / ARCHIVO_DISTRIBUCION)
        datos = copy.deepcopy(self._por_defecto)
        usuario = leer_json(CONFIG_USUARIO / ARCHIVO_DISTRIBUCION)
        for nombre, valores in usuario.get("espacios", {}).items():
            datos.setdefault("espacios", {}).setdefault(nombre, {}).update(valores)
        self.activo: str = usuario.get("espacio_activo", datos.get("espacio_activo", "minuto"))
        self.espacios: dict[str, Espacio] = {}
        for nombre, valores in datos.get("espacios", {}).items():
            tamanos = {clave: float(v) for clave, v in valores.items() if isinstance(v, (int, float))}
            self.espacios[nombre] = Espacio(nombre, tamanos, list(valores.get("visibles", PANELES)),
                                            set(valores.get("plegados", [])))
        if self.activo not in self.espacios:
            self.activo = next(iter(self.espacios), "minuto")

    @property
    def actual(self) -> Espacio:
        return self.espacios[self.activo]

    def cambiar(self, nombre: str) -> Espacio:
        if nombre in self.espacios:
            self.activo = nombre
        return self.actual

    def restablecer(self) -> None:
        """Vuelve el espacio activo a los valores del repositorio."""
        valores = self._por_defecto.get("espacios", {}).get(self.activo, {})
        espacio = self.actual
        espacio.tamanos = {clave: float(v) for clave, v in valores.items() if isinstance(v, (int, float))}
        espacio.visibles = list(valores.get("visibles", PANELES))
        espacio.plegados.clear()

    def guardar(self) -> None:
        datos = {
            "espacio_activo": self.activo,
            "espacios": {
                nombre: {**{k: round(v) for k, v in e.tamanos.items()}, "visibles": e.visibles,
                         "plegados": sorted(e.plegados)}
                for nombre, e in self.espacios.items()
            },
        }
        CONFIG_USUARIO.mkdir(parents=True, exist_ok=True)
        escribir_json(CONFIG_USUARIO / ARCHIVO_DISTRIBUCION, datos)
