"""Biblioteca de efectos de imagen.

Cada efecto recibe la imagen **no premultiplicada** en float32 (alto, ancho, 4)
con valores 0–1, sus parámetros ya evaluados en el fotograma y un contexto, y
devuelve la imagen resultante. El registro es ampliable: los plugins (E23)
agregan efectos con `registrar_efecto`.

Parámetros (convención):
- brillo `valor` −1…1 · contraste `valor` −1…1 · saturación `valor` −1…1
- temperatura `valor` −1 (frío) … 1 (cálido)
- desenfoque `radio` en px del lienzo · nitidez `cantidad` 0…2
- croma: opciones `color` (hex), parámetros `tolerancia` 0…1 y `suavidad` 0…1
- lut: opción `archivo` (en `recursos/luts/`), parámetro `intensidad` 0…1
- mascara: `centro_x`, `centro_y`, `ancho`, `alto` (fracciones), `suavidad`, `invertir`; opción `forma`
- vineta: `intensidad` 0…1, `radio`
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from editor.core.modelo.efecto import DescriptorEfecto, Efecto, registrar_tipo_efecto

registro = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextoEfecto:
    escala: float = 1.0                 # píxeles de la imagen por píxel del lienzo
    carpeta_recursos: Path | None = None


Aplicador = Callable[[np.ndarray, dict[str, float], dict[str, str], ContextoEfecto], np.ndarray]
_APLICADORES: dict[str, Aplicador] = {}


def registrar_efecto(tipo: str, aplicador: Aplicador, descriptor: DescriptorEfecto | None = None) -> None:
    registrar_tipo_efecto(tipo, descriptor)
    _APLICADORES[tipo] = aplicador


def aplicar_efectos(imagen: np.ndarray, efectos: list[Efecto], f_local: float, contexto: ContextoEfecto) -> np.ndarray:
    for efecto in efectos:
        if not efecto.activo:
            continue
        aplicador = _APLICADORES.get(efecto.tipo)
        if aplicador is None:
            registro.warning("Efecto sin implementación: %s", efecto.tipo)
            continue
        imagen = aplicador(imagen, efecto.valores_en(f_local), efecto.opciones, contexto)
    return imagen


def _luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _brillo(img, p, o, c):
    img[..., :3] = np.clip(img[..., :3] + p.get("valor", 0.0), 0, 1)
    return img


def _contraste(img, p, o, c):
    factor = 1.0 + p.get("valor", 0.0)
    img[..., :3] = np.clip((img[..., :3] - 0.5) * factor + 0.5, 0, 1)
    return img


def _saturacion(img, p, o, c):
    factor = 1.0 + p.get("valor", 0.0)
    gris = _luma(img[..., :3])[..., None]
    img[..., :3] = np.clip(gris + (img[..., :3] - gris) * factor, 0, 1)
    return img


def _temperatura(img, p, o, c):
    valor = p.get("valor", 0.0) * 0.1
    img[..., 0] = np.clip(img[..., 0] + valor, 0, 1)
    img[..., 2] = np.clip(img[..., 2] - valor, 0, 1)
    return img


def _desenfoque(img, p, o, c):
    radio = p.get("radio", 0.0) * c.escala
    if radio <= 0.3:
        return img
    # Se desenfoca premultiplicado para que los bordes transparentes no oscurezcan.
    alfa = img[..., 3:4]
    premultiplicada = np.concatenate([img[..., :3] * alfa, alfa], axis=2)
    borrosa = cv2.GaussianBlur(premultiplicada, (0, 0), sigmaX=radio / 2)
    alfa = borrosa[..., 3:4]
    rgb = np.divide(borrosa[..., :3], alfa, out=np.zeros_like(borrosa[..., :3]), where=alfa > 1e-6)
    return np.concatenate([np.clip(rgb, 0, 1), alfa], axis=2).astype(np.float32)


def _nitidez(img, p, o, c):
    cantidad = p.get("cantidad", 0.0)
    if cantidad <= 0:
        return img
    borrosa = cv2.GaussianBlur(img[..., :3], (0, 0), sigmaX=max(0.5, 1.0 * c.escala))
    img[..., :3] = np.clip(img[..., :3] + (img[..., :3] - borrosa) * cantidad, 0, 1)
    return img


def _color_hex(texto: str) -> np.ndarray:
    texto = texto.lstrip("#")
    return np.array([int(texto[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)


def _croma(img, p, o, c):
    clave = _color_hex(o.get("color", "#00ff00"))
    tolerancia = p.get("tolerancia", 0.3)
    suavidad = max(1e-3, p.get("suavidad", 0.1))
    distancia = np.linalg.norm(img[..., :3] - clave, axis=2) / np.sqrt(3)
    mascara = np.clip((distancia - tolerancia) / suavidad, 0, 1)
    img[..., 3] *= mascara
    # Quitar el reflejo del color de fondo en los bordes.
    canal = int(np.argmax(clave))
    otros = [i for i in range(3) if i != canal]
    img[..., canal] = np.minimum(img[..., canal], np.maximum(img[..., otros[0]], img[..., otros[1]]) + 0.05)
    return img


@lru_cache(maxsize=16)
def _leer_cube(ruta: Path) -> np.ndarray:
    tamano = 0
    valores: list[list[float]] = []
    for linea in ruta.read_text(encoding="utf-8", errors="ignore").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        if linea.upper().startswith("LUT_3D_SIZE"):
            tamano = int(linea.split()[1])
            continue
        partes = linea.split()
        if len(partes) == 3:
            try:
                valores.append([float(v) for v in partes])
            except ValueError:
                continue
    if tamano == 0 or len(valores) != tamano ** 3:
        raise ValueError(f"LUT .cube inválido: {ruta}")
    # En .cube el rojo varía más rápido: índice [b][g][r].
    return np.array(valores, dtype=np.float32).reshape(tamano, tamano, tamano, 3)


def _lut(img, p, o, c):
    archivo = o.get("archivo", "")
    if not archivo or c.carpeta_recursos is None:
        return img
    ruta = c.carpeta_recursos / "luts" / archivo
    if not ruta.exists():
        registro.warning("No existe el LUT %s", ruta)
        return img
    tabla = _leer_cube(ruta)
    n = tabla.shape[0] - 1
    rgb = np.clip(img[..., :3], 0, 1) * n
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    r0, g0, b0 = (np.floor(x).astype(np.int32) for x in (r, g, b))
    r1, g1, b1 = (np.minimum(x + 1, n) for x in (r0, g0, b0))
    fr, fg, fb = (x - np.floor(x) for x in (r, g, b))
    fr, fg, fb = fr[..., None], fg[..., None], fb[..., None]
    c00 = tabla[b0, g0, r0] * (1 - fr) + tabla[b0, g0, r1] * fr
    c01 = tabla[b1, g0, r0] * (1 - fr) + tabla[b1, g0, r1] * fr
    c10 = tabla[b0, g1, r0] * (1 - fr) + tabla[b0, g1, r1] * fr
    c11 = tabla[b1, g1, r0] * (1 - fr) + tabla[b1, g1, r1] * fr
    resultado = (c00 * (1 - fg) + c10 * fg) * (1 - fb) + (c01 * (1 - fg) + c11 * fg) * fb
    intensidad = p.get("intensidad", 1.0)
    img[..., :3] = img[..., :3] * (1 - intensidad) + resultado * intensidad
    return img


def _mascara(img, p, o, c):
    alto, ancho = img.shape[:2]
    cx, cy = p.get("centro_x", 0.5), p.get("centro_y", 0.5)
    rx, ry = max(1e-3, p.get("ancho", 0.6) / 2), max(1e-3, p.get("alto", 0.6) / 2)
    suavidad = max(1e-3, p.get("suavidad", 0.05))
    y, x = np.mgrid[0:alto, 0:ancho].astype(np.float32)
    dx, dy = (x / max(1, ancho - 1) - cx) / rx, (y / max(1, alto - 1) - cy) / ry
    if o.get("forma", "elipse") == "rectangulo":
        distancia = np.maximum(np.abs(dx), np.abs(dy))
    else:
        distancia = np.sqrt(dx * dx + dy * dy)
    mascara = np.clip((1 + suavidad - distancia) / suavidad, 0, 1)
    if p.get("invertir", 0) >= 0.5:
        mascara = 1 - mascara
    img[..., 3] *= mascara
    return img


def _vineta(img, p, o, c):
    alto, ancho = img.shape[:2]
    y, x = np.mgrid[0:alto, 0:ancho].astype(np.float32)
    dx, dy = x / max(1, ancho - 1) * 2 - 1, y / max(1, alto - 1) * 2 - 1
    distancia = np.sqrt(dx * dx + dy * dy) / np.sqrt(2)
    radio = max(0.05, p.get("radio", 0.8))
    oscuro = np.clip((distancia - radio * 0.5) / max(1e-3, radio), 0, 1) * p.get("intensidad", 0.5)
    img[..., :3] *= (1 - oscuro)[..., None]
    return img


for _tipo, _funcion in {
    "brillo": _brillo,
    "contraste": _contraste,
    "saturacion": _saturacion,
    "temperatura": _temperatura,
    "desenfoque": _desenfoque,
    "nitidez": _nitidez,
    "croma": _croma,
    "lut": _lut,
    "mascara": _mascara,
    "vineta": _vineta,
}.items():
    registrar_efecto(_tipo, _funcion)
