"""Atajos de teclado con contextos de foco (T12.7).

`config/atajos.json` (o su copia en `~/.config/editor/`) asocia acciones a
combinaciones como "Ctrl+Shift+Z". Flet entrega la etiqueta de la tecla
("Arrow Left", " ", "Page Up"…); aquí se normaliza.

Contextos: con el foco en un campo de texto solo funciona guardar (Ctrl+S);
deshacer, flechas, espacio y letras quedan para el campo mientras se escribe.
"""

from __future__ import annotations

from typing import Callable

from editor.core.ajustes import ARCHIVO_ATAJOS, CONFIG_REPOSITORIO, CONFIG_USUARIO, leer_json

_NOMBRES = {
    " ": "Space", "Space": "Space",
    "Arrow Left": "Left", "Arrow Right": "Right", "Arrow Up": "Up", "Arrow Down": "Down",
    "Page Up": "PageUp", "Page Down": "PageDown",
    "Delete": "Delete", "Backspace": "Backspace", "Escape": "Escape", "Enter": "Enter",
    "Home": "Home", "End": "End", "Tab": "Tab",
    "Equal": "=", "Minus": "-", "Numpad Add": "=", "Numpad Subtract": "-", "+": "=",
}
_FLECHAS = {"Left", "Right", "Up", "Down"}


def normalizar(tecla: str, ctrl: bool = False, shift: bool = False, alt: bool = False, meta: bool = False) -> str:
    nombre = _NOMBRES.get(tecla, tecla.upper() if len(tecla) == 1 else tecla)
    partes = [p for p, activo in (("Ctrl", ctrl or meta), ("Alt", alt), ("Shift", shift)) if activo]
    return "+".join(partes + [nombre])


def cargar_atajos() -> dict[str, str]:
    """combinación → acción. Los del usuario (`~/.config/editor/atajos.json`) reemplazan a los del repositorio."""
    datos: dict[str, str] = {}
    for ruta in (CONFIG_REPOSITORIO / ARCHIVO_ATAJOS, CONFIG_USUARIO / ARCHIVO_ATAJOS):
        try:
            datos.update({k: v for k, v in leer_json(ruta).items() if isinstance(v, str)})
        except (OSError, ValueError):
            pass
    combinaciones: dict[str, str] = {}
    for accion, combinacion in datos.items():
        if "Flechas" in combinacion:          # "Alt+Flechas" → Alt+Left, Alt+Right…
            for flecha in _FLECHAS:
                combinaciones[normalizar_combinacion(combinacion.replace("Flechas", flecha))] = f"{accion}:{flecha}"
        else:
            combinaciones[normalizar_combinacion(combinacion)] = accion
    return combinaciones


def normalizar_combinacion(texto: str) -> str:
    partes = texto.split("+")
    tecla = partes[-1] or "+"
    modificadores = {p.strip().lower() for p in partes[:-1]}
    return normalizar(tecla, ctrl="ctrl" in modificadores, shift="shift" in modificadores,
                      alt="alt" in modificadores)


class Teclado:
    """Traduce eventos de teclado a acciones según el foco."""

    EN_TEXTO = frozenset({"guardar"})

    def __init__(self, obtener_foco: Callable[[], str]) -> None:
        self.atajos = cargar_atajos()
        self._foco = obtener_foco
        self.acciones: dict[str, Callable[..., None]] = {}

    def registrar(self, accion: str, funcion: Callable[..., None]) -> None:
        self.acciones[accion] = funcion

    def procesar(self, tecla: str, ctrl: bool, shift: bool, alt: bool, meta: bool = False) -> bool:
        combinacion = normalizar(tecla, ctrl, shift, alt, meta)
        accion = self.atajos.get(combinacion)
        if accion is None:
            return False
        if self._foco() == "texto" and accion not in self.EN_TEXTO:
            return False
        nombre, _, argumento = accion.partition(":")
        funcion = self.acciones.get(nombre)
        if funcion is None:
            return False
        funcion(argumento) if argumento else funcion()
        return True
