"""Compositor: arma la imagen de un fotograma del capítulo (T7.4).

Para cada Elemento visible en f, de abajo hacia arriba
(`Capitulo.visuales_activos_en`):

1. Transformación evaluada en f (keyframes) + ajustes de transición.
2. Matriz final: salida ← ventana ← lienzo ← Elemento.
3. **Descarte**: si no toca la salida, no se decodifica.
4. Se decodifica al tamaño necesario (no a resolución completa si no hace falta).
5. Recorte, efectos (no premultiplicado) y premultiplicación.
6. `warpAffine` solo sobre la región de interés.
7. Opacidad y modo de mezcla sobre el fondo negro.

La misma función sirve para la vista previa (tamaño pequeño, interpolación
rápida), el render final (1280×720 o más, Lanczos) y los Shorts (una ventana
vertical del lienzo recompuesta a 720×1280).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from editor.core.espacio.geometria import Punto, Rect
from editor.core.espacio.transform import Afin, Transform
from editor.core.estandar import LIENZO_ALTO, LIENZO_ANCHO
from editor.core.modelo.capitulo import Capitulo, TransicionActiva
from editor.core.modelo.elemento import Elemento
from editor.core.motor import texto as motor_texto
from editor.core.motor.decodificador import GestorFuentes
from editor.core.motor.efectos import ContextoEfecto, aplicar_efectos
from editor.core.motor.motor_base import ErrorFuente

registro = logging.getLogger(__name__)

Resolutor = Callable[[Elemento], Path | None]
LIENZO_RECT = Rect(0, 0, LIENZO_ANCHO, LIENZO_ALTO)


@dataclass(frozen=True)
class Calidad:
    interpolacion: int
    nombre: str


VISTA_PREVIA = Calidad(cv2.INTER_LINEAR, "vista_previa")
FINAL = Calidad(cv2.INTER_LANCZOS4, "final")


@dataclass
class _Ajuste:
    """Cambios que una transición aplica a un Elemento en este fotograma."""

    opacidad: float = 1.0
    dx: float = 0.0
    dy: float = 0.0
    escala: float = 1.0
    barrido: tuple[str, float] | None = None  # (dirección, fracción visible)
    oscurecer: float = 0.0                    # fundido a negro: 0 = normal, 1 = negro


def _ajustes_transicion(transiciones: list[TransicionActiva]) -> dict[str, _Ajuste]:
    ajustes: dict[str, _Ajuste] = {}
    for activa in transiciones:
        transicion = activa.entrante.transicion_entrada
        assert transicion is not None
        p = activa.progreso
        ajuste = _Ajuste()
        signo = {"izquierda": 1, "derecha": -1, "arriba": 1, "abajo": -1}.get(transicion.direccion, 1)
        if transicion.tipo == "fundido":
            ajuste.opacidad = p
        elif transicion.tipo == "deslizamiento":
            if transicion.direccion in ("arriba", "abajo"):
                ajuste.dy = signo * (1 - p) * LIENZO_ALTO
            else:
                ajuste.dx = signo * (1 - p) * LIENZO_ANCHO
        elif transicion.tipo == "zoom":
            ajuste.opacidad = p
            ajuste.escala = 0.8 + 0.2 * p
        elif transicion.tipo == "barrido":
            ajuste.barrido = (transicion.direccion, p)
        elif transicion.tipo == "negro":
            # Primera mitad: el saliente se oscurece; segunda: el entrante aparece desde negro.
            ajuste.oscurecer = max(0.0, 1 - (p * 2 - 1)) if p > 0.5 else 1.0
            ajuste.opacidad = 1.0 if p > 0.5 else 0.0
            saliente = ajustes.setdefault(activa.saliente.id, _Ajuste())
            saliente.oscurecer = min(1.0, p * 2)
            if p > 0.5:
                saliente.opacidad = 0.0
        else:
            ajuste.opacidad = p  # tipos de plugins sin implementación visual: fundido
        ajustes[activa.entrante.id] = ajuste
    return ajustes


class Compositor:
    def __init__(
        self,
        fuentes: GestorFuentes,
        resolver: Resolutor,
        carpeta_recursos: Path | None = None,
        calidad: Calidad = VISTA_PREVIA,
    ) -> None:
        self.fuentes = fuentes
        self.resolver = resolver
        self.carpeta_recursos = carpeta_recursos
        self.calidad = calidad

    # --- API ---------------------------------------------------------------------------

    def componer(
        self,
        capitulo: Capitulo,
        f: int,
        tamano: tuple[int, int] = (LIENZO_ANCHO, LIENZO_ALTO),
        ventana: Rect = LIENZO_RECT,
        idioma: str | None = None,
    ) -> np.ndarray:
        """Imagen RGB uint8 de (alto, ancho) del fotograma f vista a través de `ventana`.

        `idioma`: además de lo común, los subtítulos (capas T con idioma) de ese idioma.
        """
        ancho, alto = tamano
        base = Afin.escala(ancho / ventana.ancho, alto / ventana.alto) @ Afin.traslacion(-ventana.x, -ventana.y)
        lienzo = np.zeros((alto, ancho, 3), dtype=np.float32)
        ajustes = _ajustes_transicion(capitulo.transiciones_activas(f))
        for elemento in capitulo.visuales_activos_en(f, idioma):
            try:
                self._dibujar(lienzo, elemento, f, base, ajustes.get(elemento.id))
            except ErrorFuente as error:
                registro.warning("Elemento %s sin fuente: %s", elemento.id, error)
                self._fuera_de_linea(lienzo, elemento, f, base)
        return (np.clip(lienzo, 0, 1) * 255 + 0.5).astype(np.uint8)

    # --- Un Elemento -------------------------------------------------------------------

    def _dibujar(self, lienzo: np.ndarray, elemento: Elemento, f: int, base: Afin, ajuste: _Ajuste | None) -> None:
        transform = elemento.transform_en(f)
        ajuste = ajuste or _Ajuste()
        f_local = elemento.local(f)
        caracteres = None
        if elemento.es_texto and elemento.texto is not None:
            estado = motor_texto.animacion(elemento.texto, f_local, elemento.duracion)
            ajuste.opacidad *= estado.opacidad
            ajuste.dy += estado.desplazamiento_y
            ajuste.escala *= estado.escala
            caracteres = estado.caracteres
        opacidad = transform.opacidad * ajuste.opacidad
        if opacidad <= 0.001:
            return

        # Tamaño natural y fuente de píxeles.
        if elemento.es_texto:
            escala_render = max(abs(transform.escala_x), abs(transform.escala_y)) * ajuste.escala * math.hypot(base.a, base.d)
            escala_render = max(escala_render, 0.05)
            carpeta = self.carpeta_recursos / "fuentes" if self.carpeta_recursos else None
            imagen = motor_texto.dibujar(elemento.texto, escala_render, carpeta, caracteres)  # type: ignore[arg-type]
            natural_ancho, natural_alto = imagen.shape[1] / escala_render, imagen.shape[0] / escala_render
            ruta = None
        else:
            ruta = self.resolver(elemento)
            if ruta is None:
                raise ErrorFuente(f"sin archivo para {elemento.id}")
            info = self.fuentes.info(ruta)
            natural_ancho, natural_alto = info.ancho, info.alto
            imagen = None

        matriz = self._matriz(base, transform, ajuste, natural_ancho, natural_alto)
        region_fuente = transform.recorte.region_visible(natural_ancho, natural_alto)
        if region_fuente.vacio:
            return
        roi = self._region_interes(matriz, region_fuente, lienzo.shape[1], lienzo.shape[0], ajuste)
        if roi is None:
            return

        if imagen is None:
            escala_dec = min(1.0, max(math.hypot(matriz.a, matriz.d), math.hypot(matriz.b, matriz.e)) * 1.05)
            tamano = (max(1, round(natural_ancho * escala_dec)), max(1, round(natural_alto * escala_dec)))
            assert ruta is not None
            imagen = self.fuentes.fotograma(ruta, elemento.fotograma_fuente(f), tamano)
        kx = imagen.shape[1] / natural_ancho
        ky = imagen.shape[0] / natural_alto
        matriz_fuente = matriz @ Afin.escala(1 / kx, 1 / ky)

        fuente = imagen.astype(np.float32) / 255.0
        if not transform.recorte.nulo:
            fuente = self._recortar(fuente, region_fuente, kx, ky)
        if elemento.efectos:
            fuente = aplicar_efectos(
                fuente, elemento.efectos, f_local,
                ContextoEfecto(escala=kx, carpeta_recursos=self.carpeta_recursos),
            )
        if ajuste.oscurecer > 0:
            fuente[..., :3] *= (1 - ajuste.oscurecer)
        fuente[..., :3] *= fuente[..., 3:4]  # premultiplicar

        x0, y0, x1, y1 = roi
        matriz_roi = Afin.traslacion(-x0, -y0) @ matriz_fuente
        deformada = cv2.warpAffine(
            fuente, np.array(matriz_roi.como_lista(), dtype=np.float64), (x1 - x0, y1 - y0),
            flags=self.calidad.interpolacion, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0),
        )
        if deformada.ndim == 2:
            return
        deformada *= opacidad
        self._mezclar(lienzo[y0:y1, x0:x1], deformada, transform.mezcla)

    @staticmethod
    def _matriz(base: Afin, transform: Transform, ajuste: _Ajuste, ancho: float, alto: float) -> Afin:
        matriz = base @ Afin.traslacion(ajuste.dx, ajuste.dy)
        if ajuste.escala != 1.0:
            centro = transform.matriz().aplicar(Punto(ancho / 2, alto / 2))
            matriz = (
                matriz @ Afin.traslacion(centro.x, centro.y) @ Afin.escala(ajuste.escala)
                @ Afin.traslacion(-centro.x, -centro.y)
            )
        return matriz @ transform.matriz()

    @staticmethod
    def _region_interes(matriz: Afin, region: Rect, ancho: int, alto: int, ajuste: _Ajuste) -> tuple[int, int, int, int] | None:
        ocupado = Rect.envolvente(matriz.aplicar(p) for p in region.esquinas())
        salida = Rect(0, 0, ancho, alto)
        if ajuste.barrido is not None:
            direccion, visible = ajuste.barrido
            if direccion == "derecha":
                salida = Rect(ancho * (1 - visible), 0, ancho * visible, alto)
            elif direccion == "arriba":
                salida = Rect(0, 0, ancho, alto * visible)
            elif direccion == "abajo":
                salida = Rect(0, alto * (1 - visible), ancho, alto * visible)
            else:
                salida = Rect(0, 0, ancho * visible, alto)
        interseccion = ocupado.interseccion(salida)
        if interseccion is None:
            return None
        x0 = max(0, math.floor(interseccion.izquierda))
        y0 = max(0, math.floor(interseccion.arriba))
        x1 = min(ancho, math.ceil(interseccion.derecha))
        y1 = min(alto, math.ceil(interseccion.abajo))
        if x1 <= x0 or y1 <= y0:
            return None
        return x0, y0, x1, y1

    @staticmethod
    def _recortar(fuente: np.ndarray, region: Rect, kx: float, ky: float) -> np.ndarray:
        izquierda, arriba = round(region.izquierda * kx), round(region.arriba * ky)
        derecha, abajo = round(region.derecha * kx), round(region.abajo * ky)
        fuente[:arriba, :, 3] = 0
        fuente[abajo:, :, 3] = 0
        fuente[:, :izquierda, 3] = 0
        fuente[:, derecha:, 3] = 0
        return fuente

    @staticmethod
    def _mezclar(destino: np.ndarray, fuente: np.ndarray, modo: str) -> None:
        """Mezcla premultiplicada sobre un fondo opaco (alfa de destino = 1)."""
        color = fuente[..., :3]
        alfa = fuente[..., 3:4]
        if modo == "multiplicar":
            destino[:] = color * destino + destino * (1 - alfa)
        elif modo == "pantalla":
            destino[:] = color + destino - color * destino
        elif modo == "sumar":
            destino[:] = np.minimum(1.0, destino + color)
        elif modo == "superponer":
            directo = np.divide(color, alfa, out=np.zeros_like(color), where=alfa > 1e-6)
            superpuesto = np.where(destino < 0.5, 2 * destino * directo, 1 - 2 * (1 - destino) * (1 - directo))
            destino[:] = destino * (1 - alfa) + superpuesto * alfa
        else:
            destino[:] = color + destino * (1 - alfa)

    def _fuera_de_linea(self, lienzo: np.ndarray, elemento: Elemento, f: int, base: Afin) -> None:
        """Marco rojo semitransparente donde iría un medio que falta (PROJECT.md, 8.6)."""
        transform = elemento.transform_en(f)
        ancho = elemento.ancho or LIENZO_ANCHO // 4
        alto = elemento.alto or LIENZO_ALTO // 4
        matriz = base @ transform.matriz()
        roi = self._region_interes(matriz, Rect(0, 0, ancho, alto), lienzo.shape[1], lienzo.shape[0], _Ajuste())
        if roi is None:
            return
        x0, y0, x1, y1 = roi
        zona = lienzo[y0:y1, x0:x1]
        zona[:] = zona * 0.4 + np.array([0.8, 0.05, 0.05], dtype=np.float32) * 0.6
