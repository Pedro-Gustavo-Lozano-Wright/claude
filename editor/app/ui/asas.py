"""Control espacial: asas, ancla, imán y guías.

Geometría pura (sin Flet salvo el dibujo): convierte entre píxeles del
monitor y píxeles del lienzo, detecta qué asa hay bajo el puntero y calcula la
Transform resultante de un arrastre. El comando lo decide el monitor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import flet as ft
import flet.canvas as cv

from editor.app.ui.tema import TEMA
from editor.core.espacio.geometria import Punto, Rect, iman_rect
from editor.core.espacio.lienzo import LIENZO
from editor.core.espacio.transform import Transform
from editor.core.modelo.elemento import Elemento

MOVER = "mover"
GIRAR = "girar"
ANCLA = "ancla"
ESQUINAS = ("escala_no", "escala_ne", "escala_se", "escala_so")
RADIO_ASA_PX = 7
DISTANCIA_GIRO_PX = 26
IMAN_PX = 8
MARGEN_MESA = 0.06   # con zoom "encajar" queda un borde de mesa alrededor del lienzo


# --- Vista del lienzo en el monitor ------------------------------------------------

@dataclass(frozen=True)
class VistaLienzo:
    """Dónde cae el lienzo dentro del área del monitor."""

    area_ancho: float
    area_alto: float
    zoom: float = 0.0          # 0 = encajar; 1 = 100 %

    @property
    def factor(self) -> float:
        if self.zoom > 0:
            return self.zoom
        encaje = min(self.area_ancho / LIENZO.ancho, self.area_alto / LIENZO.alto)
        return max(0.01, encaje * (1 - 2 * MARGEN_MESA))

    @property
    def origen(self) -> Punto:
        return Punto((self.area_ancho - LIENZO.ancho * self.factor) / 2,
                     (self.area_alto - LIENZO.alto * self.factor) / 2)

    def a_pantalla(self, p: Punto) -> Punto:
        o = self.origen
        return Punto(o.x + p.x * self.factor, o.y + p.y * self.factor)

    def a_lienzo(self, x: float, y: float) -> Punto:
        o = self.origen
        return Punto((x - o.x) / self.factor, (y - o.y) / self.factor)

    @property
    def rect_lienzo(self) -> Rect:
        o = self.origen
        return Rect(o.x, o.y, LIENZO.ancho * self.factor, LIENZO.alto * self.factor)


# --- Tamaño y contorno de un Elemento ------------------------------------------------

_TAMANOS_TEXTO: dict[tuple, tuple[float, float]] = {}


def tamano_natural(elemento: Elemento, carpeta_fuentes: Path | None = None) -> tuple[float, float]:
    """Tamaño en píxeles del Elemento sin transformar (texto: el de su imagen a escala 1)."""
    if elemento.es_texto and elemento.texto is not None:
        from editor.core.motor import texto as motor_texto

        clave = (repr(elemento.texto), str(carpeta_fuentes or ""))
        if clave not in _TAMANOS_TEXTO:
            if len(_TAMANOS_TEXTO) > 64:
                _TAMANOS_TEXTO.clear()
            imagen = motor_texto.dibujar(elemento.texto, 1.0, carpeta_fuentes)
            _TAMANOS_TEXTO[clave] = (float(imagen.shape[1]), float(imagen.shape[0]))
        return _TAMANOS_TEXTO[clave]
    return float(elemento.ancho or LIENZO.ancho), float(elemento.alto or LIENZO.alto)


@dataclass(frozen=True)
class Contorno:
    """Esquinas visibles del Elemento y su ancla, en píxeles del lienzo."""

    esquinas: tuple[Punto, ...]   # no, ne, se, so
    ancla: Punto
    transform: Transform
    tamano: tuple[float, float]

    @classmethod
    def de(cls, elemento: Elemento, f: int, tamano: tuple[float, float]) -> "Contorno":
        transform = elemento.transform_en(f)
        esquinas = LIENZO.esquinas(transform, *tamano)
        return cls(esquinas, Punto(transform.x, transform.y), transform, tamano)

    @classmethod
    def con_transform(cls, transform: Transform, tamano: tuple[float, float]) -> "Contorno":
        return cls(LIENZO.esquinas(transform, *tamano), Punto(transform.x, transform.y), transform, tamano)

    @property
    def rect(self) -> Rect:
        return Rect.envolvente(self.esquinas)

    def asa_giro(self, vista: VistaLienzo) -> Punto:
        """Punto de giro: sobre el centro del borde superior, hacia afuera."""
        no, ne = self.esquinas[0], self.esquinas[1]
        medio = Punto((no.x + ne.x) / 2, (no.y + ne.y) / 2)
        centro = Punto(sum(p.x for p in self.esquinas) / 4, sum(p.y for p in self.esquinas) / 4)
        dx, dy = medio.x - centro.x, medio.y - centro.y
        largo = math.hypot(dx, dy) or 1.0
        distancia = DISTANCIA_GIRO_PX / vista.factor
        return Punto(medio.x + dx / largo * distancia, medio.y + dy / largo * distancia)


def dentro(poligono: tuple[Punto, ...], p: Punto) -> bool:
    dentro = False
    j = len(poligono) - 1
    for i, a in enumerate(poligono):
        b = poligono[j]
        if (a.y > p.y) != (b.y > p.y) and p.x < (b.x - a.x) * (p.y - a.y) / ((b.y - a.y) or 1e-9) + a.x:
            dentro = not dentro
        j = i
    return dentro


def asa_en(contorno: Contorno, vista: VistaLienzo, x: float, y: float) -> str | None:
    """Qué asa hay en (x, y) del monitor, o None."""
    punto = Punto(x, y)
    cerca = lambda p: vista.a_pantalla(p).distancia(punto) <= RADIO_ASA_PX + 2  # noqa: E731
    if cerca(contorno.ancla):
        return ANCLA
    if cerca(contorno.asa_giro(vista)):
        return GIRAR
    for nombre, esquina in zip(ESQUINAS, contorno.esquinas):
        if cerca(esquina):
            return nombre
    if dentro(contorno.esquinas, vista.a_lienzo(x, y)):
        return MOVER
    return None


# --- Arrastres ---------------------------------------------------------------------

def guias(otros: list[Rect]) -> tuple[list[float], list[float]]:
    """Guías de imán: bordes y centro del lienzo, márgenes seguros y otros Elementos."""
    xs, ys = (list(v) for v in LIENZO.guias())
    for porcentaje in (0.05, 0.10):
        seguro = LIENZO.margen_seguro(porcentaje)
        xs += [seguro.izquierda, seguro.derecha]
        ys += [seguro.arriba, seguro.abajo]
    for rect in otros:
        xs += [rect.izquierda, rect.centro.x, rect.derecha]
        ys += [rect.arriba, rect.centro.y, rect.abajo]
    return xs, ys


def arrastrar(
    asa: str,
    original: Contorno,
    desde: Punto,
    hasta: Punto,
    vista: VistaLienzo,
    libre: bool = False,
    iman: bool = True,
    otros: list[Rect] | None = None,
) -> Transform:
    """Transform tras arrastrar `asa` de `desde` a `hasta` (píxeles del lienzo).

    `libre` (Shift): escala sin mantener la proporción y giro sin pasos de 15°.
    """
    t = original.transform
    if asa == MOVER:
        dx, dy = hasta.x - desde.x, hasta.y - desde.y
        if iman:
            movido = Rect(original.rect.x + dx, original.rect.y + dy, original.rect.ancho, original.rect.alto)
            gx, gy = guias(otros or [])
            ajuste_x, ajuste_y = iman_rect(movido, gx, gy, IMAN_PX / vista.factor)
            dx, dy = dx + ajuste_x, dy + ajuste_y
        return t.con(x=t.x + dx, y=t.y + dy)
    if asa == GIRAR:
        a0 = math.atan2(desde.y - t.y, desde.x - t.x)
        a1 = math.atan2(hasta.y - t.y, hasta.x - t.x)
        angulo = t.rotacion + math.degrees(a1 - a0)
        if not libre:
            angulo = round(angulo / 15) * 15
        return t.con(rotacion=((angulo + 180) % 360) - 180)
    if asa in ESQUINAS:
        inversa = t.matriz().inversa()
        esquina = inversa.aplicar(original.esquinas[ESQUINAS.index(asa)])
        local = inversa.aplicar(hasta)
        base_x, base_y = esquina.x - t.ancla_x, esquina.y - t.ancla_y
        fx = (local.x - t.ancla_x) / base_x if abs(base_x) > 1e-6 else 1.0
        fy = (local.y - t.ancla_y) / base_y if abs(base_y) > 1e-6 else 1.0
        if not libre:
            fx = fy = max(fx, fy, key=abs) if abs(base_x) > 1e-6 and abs(base_y) > 1e-6 else (fx if abs(base_x) > 1e-6 else fy)
        return t.con(escala_x=_escala(t.escala_x * fx), escala_y=_escala(t.escala_y * fy))
    raise ValueError(f"Asa desconocida: {asa}")


def ancla_local(original: Contorno, hasta: Punto) -> tuple[float, float]:
    """Nueva ancla (coordenadas del Elemento) al soltarla en `hasta` del lienzo."""
    local = original.transform.matriz().inversa().aplicar(hasta)
    return local.x, local.y


def _escala(valor: float) -> float:
    return math.copysign(max(abs(valor), 0.01), valor if valor else 1.0)


def mover_teclado(transform: Transform, direccion: str, pixeles: float) -> Transform:
    dx = {"Left": -pixeles, "Right": pixeles}.get(direccion, 0.0)
    dy = {"Up": -pixeles, "Down": pixeles}.get(direccion, 0.0)
    return transform.con(x=transform.x + dx, y=transform.y + dy)


# --- Dibujo ------------------------------------------------------------------------

def _pintura(color: str, grosor: float = 1.0, relleno: bool = False, opacidad: float = 1.0) -> ft.Paint:
    return ft.Paint(
        color=ft.Colors.with_opacity(opacidad, color),
        stroke_width=grosor,
        style=ft.PaintingStyle.FILL if relleno else ft.PaintingStyle.STROKE,
    )


def formas_lienzo(vista: VistaLienzo, margenes: bool, guia_vertical: bool, ventana_short=None) -> list[cv.Shape]:
    """Borde del lienzo, márgenes seguros y guía 9:16 (centrada, o la ventana del Short elegido)."""
    r = vista.rect_lienzo
    formas: list[cv.Shape] = [cv.Rect(r.x, r.y, r.ancho, r.alto, paint=_pintura(TEMA.borde, 1))]
    if margenes:
        for porcentaje in (0.05, 0.10):
            s = LIENZO.margen_seguro(porcentaje)
            o = vista.a_pantalla(Punto(s.x, s.y))
            formas.append(cv.Rect(o.x, o.y, s.ancho * vista.factor, s.alto * vista.factor,
                                  paint=_pintura(TEMA.margen_seguro, 1, opacidad=0.25)))
    if guia_vertical or ventana_short is not None:
        v = ventana_short or LIENZO.ventana_vertical(LIENZO.x_ventana_centrada())
        o = vista.a_pantalla(Punto(v.x, v.y))
        formas.append(cv.Rect(o.x, o.y, v.ancho * vista.factor, v.alto * vista.factor,
                              paint=_pintura(TEMA.guia, 1.5, opacidad=0.8)))
    return formas


def formas_contorno(contorno: Contorno, vista: VistaLienzo, con_asas: bool = True) -> list[cv.Shape]:
    puntos = [vista.a_pantalla(p) for p in contorno.esquinas]
    formas: list[cv.Shape] = []
    for a, b in zip(puntos, puntos[1:] + puntos[:1]):
        formas.append(cv.Line(a.x, a.y, b.x, b.y, paint=_pintura(TEMA.seleccion, 1.5)))
    if not con_asas:
        return formas
    for p in puntos:
        formas.append(cv.Rect(p.x - RADIO_ASA_PX / 2, p.y - RADIO_ASA_PX / 2, RADIO_ASA_PX, RADIO_ASA_PX,
                              paint=_pintura(TEMA.seleccion, relleno=True)))
    giro = vista.a_pantalla(contorno.asa_giro(vista))
    medio = Punto((puntos[0].x + puntos[1].x) / 2, (puntos[0].y + puntos[1].y) / 2)
    formas.append(cv.Line(medio.x, medio.y, giro.x, giro.y, paint=_pintura(TEMA.seleccion, 1)))
    formas.append(cv.Circle(giro.x, giro.y, RADIO_ASA_PX / 2 + 1, paint=_pintura(TEMA.acento, relleno=True)))
    ancla = vista.a_pantalla(contorno.ancla)
    formas.append(cv.Circle(ancla.x, ancla.y, RADIO_ASA_PX / 2 + 2, paint=_pintura(TEMA.acento, 2)))
    formas.append(cv.Line(ancla.x - 6, ancla.y, ancla.x + 6, ancla.y, paint=_pintura(TEMA.acento, 1)))
    formas.append(cv.Line(ancla.x, ancla.y - 6, ancla.x, ancla.y + 6, paint=_pintura(TEMA.acento, 1)))
    return formas
