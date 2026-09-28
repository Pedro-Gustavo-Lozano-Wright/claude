"""Edición en la timeline: geometría, imán y comandos por herramienta (E14).

La timeline de un minuto muestra 60 s (1440 fotogramas); con más zoom, una
ventana menor que se desplaza. Este módulo traduce píxeles ↔ fotogramas y
gestos → comandos, sin depender de Flet.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from editor.app.estado import Sesion
from editor.core.comandos import (
    INICIO,
    FIN,
    Alcance,
    DividirElementos,
    DuplicarElemento,
    IntercambiarMinutos,
    CambiarPropiedad,
    CambiarTransicion,
    MoverElemento,
    MoverElementos,
    PegarElementos,
    PonerKeyframe,
    PonerMarcador,
    QuitarElementos,
    QuitarRango,
    RecortarElemento,
    RippleRecorte,
    Roll,
    Slide,
    Slip,
)
from editor.core.comandos.agregar_elemento import AgregarElemento
from editor.core.comandos.fabrica import elemento_texto
from editor.core.comandos.operaciones import ModoColocacion
from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO, FOTOGRAMAS_POR_MINUTO, FPS
from editor.core.modelo.capa import Capa, TipoCapa, todas_las_capas
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.keyframe import Keyframe
from editor.core.modelo.marcador import Marcador
from editor.core.modelo.transicion import Transicion

FOTOGRAMAS_VISIBLES = {
    "capitulo": FOTOGRAMAS_POR_CAPITULO,
    "minuto": FOTOGRAMAS_POR_MINUTO,
    "segundos": 10 * FPS,
    "fotograma": FPS,
}
BORDE_RECORTE_PX = 6
IMAN_PX = 8


@dataclass(frozen=True)
class Pista:
    """Una fila de la timeline: una capa de los minutos o de Global."""

    capa: Capa
    en_global: bool

    @property
    def etiqueta(self) -> str:
        return f"G·{self.capa.codigo}" if self.en_global else self.capa.codigo


def pistas_visibles(sesion: Sesion) -> list[Pista]:
    """Capas con contenido (más V1, V2, T1 y A1 siempre), de arriba hacia abajo: textos, videos, audio, Global."""
    capitulo = sesion.capitulo
    usadas = {(e.capa, e.en_global) for e in capitulo.todos_los_elementos()}
    base = {(Capa.desde_codigo(c), False) for c in ("T1", "V2", "V1", "A1")}
    todas = usadas | base
    def orden(item):
        capa, en_global = item
        grupo = {TipoCapa.TEXTO: 0, TipoCapa.VIDEO: 1, TipoCapa.AUDIO: 2}[capa.tipo]
        return (1 if en_global else 0, grupo, -capa.numero if capa.tipo is not TipoCapa.AUDIO else capa.numero)
    return [Pista(capa, en_global) for capa, en_global in sorted(todas, key=orden)]


@dataclass
class Vista:
    """Conversión entre fotogramas del capítulo y píxeles de la timeline."""

    inicio: int
    fotogramas: int
    ancho_px: float

    @classmethod
    def de(cls, sesion: Sesion, ancho_px: float) -> "Vista":
        zoom = sesion.estado.zoom_timeline
        visibles = FOTOGRAMAS_VISIBLES[zoom]
        if zoom == "capitulo":
            inicio = 0
        elif zoom == "minuto":
            inicio = sesion.estado.minuto * FOTOGRAMAS_POR_MINUTO
        else:
            inicio = max(0, min(sesion.estado.desplazamiento_timeline, FOTOGRAMAS_POR_CAPITULO - visibles))
        return cls(inicio, visibles, max(1.0, ancho_px))

    @property
    def fin(self) -> int:
        return self.inicio + self.fotogramas

    def x(self, f: float) -> float:
        return (f - self.inicio) / self.fotogramas * self.ancho_px

    def f(self, x: float) -> int:
        return round(self.inicio + x / self.ancho_px * self.fotogramas)

    def px_por_fotograma(self) -> float:
        return self.ancho_px / self.fotogramas


def elementos_de_pista(sesion: Sesion, pista: Pista, vista: Vista) -> list[Elemento]:
    capitulo = sesion.capitulo
    fuente = capitulo.global_ if pista.en_global else capitulo.elementos_de_minutos()
    return sorted(
        (e for e in fuente if e.capa == pista.capa and e.inicio < vista.fin and vista.inicio < e.fin),
        key=lambda e: e.inicio,
    )


def puntos_de_iman(sesion: Sesion, vista: Vista, ignorar: set[str]) -> list[int]:
    """Cortes de Elementos, marcadores, cabezal e inicio de cada minuto visibles."""
    capitulo = sesion.capitulo
    puntos = {sesion.estado.cabezal}
    for elemento in capitulo.todos_los_elementos():
        if elemento.id not in ignorar and elemento.inicio < vista.fin and vista.inicio < elemento.fin:
            puntos.update((elemento.inicio, elemento.fin))
    puntos.update(m.f for m in capitulo.marcadores_en_rango(vista.inicio, vista.fin))
    puntos.update(range((vista.inicio // FOTOGRAMAS_POR_MINUTO) * FOTOGRAMAS_POR_MINUTO, vista.fin + 1, FOTOGRAMAS_POR_MINUTO))
    return sorted(puntos)


def iman(sesion: Sesion, vista: Vista, f: int, ignorar: set[str]) -> int:
    if not sesion.estado.iman:
        return f
    tolerancia = IMAN_PX / vista.px_por_fotograma()
    mejor = min(puntos_de_iman(sesion, vista, ignorar), key=lambda p: abs(p - f), default=f)
    return mejor if abs(mejor - f) <= tolerancia else f


# --- Gestos → comandos ------------------------------------------------------------------

def zona_de(elemento: Elemento, vista: Vista, x: float) -> str:
    """'inicio', 'fin' o 'cuerpo' según dónde cae el puntero sobre el Elemento."""
    if abs(x - vista.x(elemento.inicio)) <= BORDE_RECORTE_PX:
        return INICIO
    if abs(x - vista.x(elemento.fin)) <= BORDE_RECORTE_PX:
        return FIN
    return "cuerpo"


def vecino_contiguo(sesion: Sesion, elemento: Elemento, lado: str) -> Elemento | None:
    fuente = sesion.capitulo.global_ if elemento.en_global else sesion.capitulo.elementos_de_minutos()
    for otro in fuente:
        if otro.id != elemento.id and otro.capa == elemento.capa:
            if lado == FIN and otro.inicio == elemento.fin:
                return otro
            if lado == INICIO and otro.fin == elemento.inicio:
                return otro
    return None


def arrastrar(sesion: Sesion, elemento: Elemento, zona: str, original: Elemento, delta_f: int,
              vista: Vista, pista_destino: Pista | None = None,
              originales_grupo: dict[str, Elemento] | None = None) -> bool:
    """Aplica un arrastre según la herramienta. `original` es el Elemento al empezar el gesto;
    `originales_grupo`, la selección múltiple al empezar (se mueve entera con el cuerpo)."""
    estado = sesion.estado
    capitulo = estado.capitulo
    herramienta = estado.herramienta
    ignorar = {elemento.id}
    if herramienta == "slip" and zona == "cuerpo":
        return sesion.ejecutar(Slip(capitulo, elemento.id, max(0, original.tiempo.fuente_entrada - delta_f)))
    if herramienta == "slide" and zona == "cuerpo":
        return sesion.ejecutar(Slide(capitulo, elemento.id, iman(sesion, vista, original.inicio + delta_f, ignorar)))
    if zona in (INICIO, FIN):
        borde = original.inicio if zona == INICIO else original.fin
        nuevo = iman(sesion, vista, borde + delta_f, ignorar)
        if herramienta == "roll":
            vecino = vecino_contiguo(sesion, elemento, zona)
            if vecino is not None:
                izquierdo, derecho = (vecino, elemento) if zona == INICIO else (elemento, vecino)
                return sesion.ejecutar(Roll(capitulo, izquierdo.id, derecho.id, nuevo))
        if herramienta == "ripple":
            delta = (nuevo - borde) if zona == INICIO else (borde - nuevo)
            return sesion.ejecutar(RippleRecorte(capitulo, elemento.id, zona, delta))
        return sesion.ejecutar(RecortarElemento(capitulo, elemento.id, zona, nuevo))
    grupo = originales_grupo if herramienta == "seleccion" and originales_grupo and len(originales_grupo) > 1 else None
    if grupo is not None and original.id in grupo:
        # Selección múltiple: todos se mueven lo mismo que el arrastrado (con imán en el arrastrado).
        ignorar = set(grupo)
        desplazamiento = iman(sesion, vista, original.inicio + delta_f, ignorar) - original.inicio
        desplazamiento = max(desplazamiento, -min(g.inicio for g in grupo.values()))
        return sesion.ejecutar(lambda: MoverElementos(capitulo, {i: g.inicio + desplazamiento for i, g in grupo.items()}))
    nuevo_inicio = iman(sesion, vista, original.inicio + delta_f, ignorar)
    nueva_capa = None
    if pista_destino is not None and pista_destino.en_global == elemento.en_global \
            and pista_destino.capa.tipo is elemento.capa.tipo and pista_destino.capa != elemento.capa:
        nueva_capa = pista_destino.capa
    return sesion.ejecutar(MoverElemento(capitulo, elemento.id, max(0, nuevo_inicio), nueva_capa))


def cortar_en(sesion: Sesion, f: int, id_elemento: str | None = None) -> bool:
    ids = [id_elemento] if id_elemento else None
    return sesion.ejecutar(DividirElementos(sesion.estado.capitulo, f, ids))


def quitar_seleccion(sesion: Sesion, ripple: bool = False) -> bool:
    ids = sorted(sesion.estado.seleccion)
    if not ids:
        return False
    if sesion.ejecutar(QuitarElementos(sesion.estado.capitulo, ids, ripple=ripple, alcance=Alcance.MINUTO)):
        sesion.estado.seleccion.clear()
        return True
    return False


def copiar(sesion: Sesion) -> int:
    sesion.estado.portapapeles = [copy.deepcopy(e) for e in sesion.seleccionados()]
    return len(sesion.estado.portapapeles)


def pegar(sesion: Sesion, modo: ModoColocacion = ModoColocacion.RECHAZAR) -> bool:
    elementos = sesion.estado.portapapeles
    if not elementos:
        return False
    delta = sesion.estado.cabezal - min(e.inicio for e in elementos)
    return sesion.ejecutar(PegarElementos(sesion.estado.capitulo, elementos, delta, modo))


def duplicar(sesion: Sesion) -> bool:
    elemento = sesion.seleccionado()
    if elemento is None:
        return False
    return sesion.ejecutar(DuplicarElemento(sesion.estado.capitulo, elemento, elemento.fin))


def poner_marcador(sesion: Sesion, nombre: str = "") -> bool:
    return sesion.ejecutar(PonerMarcador(sesion.estado.capitulo, Marcador(sesion.estado.cabezal, nombre)))


def intercambiar_minutos(sesion: Sesion, a: int, b: int) -> bool:
    return sesion.ejecutar(IntercambiarMinutos(sesion.estado.capitulo, a, b))


def capas_de_tipo(tipo: TipoCapa) -> list[str]:
    return [c.codigo for c in todas_las_capas(tipo)]


def quitar_rango(sesion: Sesion, extraer: bool) -> bool:
    """Quita lo que hay entre las marcas I y O en las capas de los minutos; `extraer` cierra el hueco."""
    estado = sesion.estado
    if estado.entrada is None or estado.salida is None or estado.salida <= estado.entrada:
        sesion.avisar("Marque entrada (I) y salida (O) en la timeline.")
        return False
    capas = sorted({p.capa for p in pistas_visibles(sesion) if not p.en_global}, key=lambda c: c.codigo)
    return sesion.ejecutar(lambda: QuitarRango(estado.capitulo, estado.entrada, estado.salida, capas, extraer))


def agregar_texto(sesion: Sesion, texto: str = "Título", codigo_capa: str = "T1", plantilla: str | None = None) -> bool:
    capa = Capa.desde_codigo(codigo_capa)
    try:
        duracion = FPS * 3
        if plantilla is not None:
            from editor.core.modelo.plantillas_texto import PLANTILLAS

            duracion = FPS * PLANTILLAS[plantilla].duracion_segundos
        elemento = elemento_texto(sesion.proyecto, capa, sesion.estado.cabezal, texto, duracion=duracion,
                                  plantilla=plantilla)
    except ValueError as error:
        sesion.avisar(str(error))
        return False
    if sesion.ejecutar(AgregarElemento(sesion.estado.capitulo, elemento)):
        sesion.estado.seleccion = {elemento.id}
        return True
    return False


# --- E17: búsqueda, transiciones y volumen en la timeline -------------------------------

def buscar(sesion: Sesion, texto: str, desde_id: str | None = None) -> Elemento | None:
    """Siguiente Elemento del capítulo cuyo nombre contiene `texto` (en orden de tiempo, circular)."""
    texto = texto.strip().lower()
    if not texto:
        return None
    candidatos = sorted((e for e in sesion.capitulo.todos_los_elementos() if texto in e.nombre.lower()),
                        key=lambda e: (e.inicio, e.capa.codigo, e.id))
    if not candidatos:
        return None
    ids = [e.id for e in candidatos]
    siguiente = (ids.index(desde_id) + 1) % len(ids) if desde_id in ids else 0
    return candidatos[siguiente]


def cambiar_transicion(sesion: Sesion, id_elemento: str, tipo: str | None, duracion: int | None = None,
                       direccion: str | None = None) -> bool:
    """`tipo=None` quita la transición de entrada. Los demás valores conservan los actuales si faltan."""
    elemento = sesion.capitulo.buscar(id_elemento)
    if elemento is None:
        return False
    if tipo is None:
        transicion = None
    else:
        actual = elemento.transicion_entrada
        transicion = Transicion(
            tipo=tipo,
            duracion=duracion if duracion is not None else (actual.duracion if actual else 12),
            direccion=direccion if direccion is not None else (actual.direccion if actual else "izquierda"),
        )
    return sesion.ejecutar(lambda: CambiarTransicion(sesion.estado.capitulo, id_elemento, transicion))


VOLUMEN_MAXIMO = 2.0


def volumen_desde_altura(y_relativa: float) -> float:
    """0 arriba = volumen máximo (200 %), 1 abajo = silencio. La línea del 100 % queda a media altura."""
    return round(max(0.0, min(VOLUMEN_MAXIMO, (1.0 - y_relativa) * VOLUMEN_MAXIMO)), 3)


def altura_de_volumen(volumen: float) -> float:
    return 1.0 - max(0.0, min(VOLUMEN_MAXIMO, volumen)) / VOLUMEN_MAXIMO


def fijar_volumen(sesion: Sesion, id_elemento: str, volumen: float) -> bool:
    """Arrastre vertical con Alt en un Elemento de audio: con keyframes de volumen pone uno en el
    cabezal; sin ellos cambia el volumen base. Valores absolutos: el arrastre se fusiona."""
    elemento = sesion.capitulo.buscar(id_elemento)
    if elemento is None or not elemento.suena:
        return False
    capitulo = sesion.estado.capitulo
    if elemento.animacion.tiene("volumen"):
        f_local = min(max(0, sesion.estado.cabezal - elemento.inicio), elemento.duracion - 1)
        previo = elemento.animacion.pista("volumen").obtener(f_local)
        keyframe = Keyframe(f_local, volumen, previo.curva if previo else "lineal", previo.controles if previo else None)
        return sesion.ejecutar(lambda: PonerKeyframe(capitulo, id_elemento, "volumen", keyframe))
    return sesion.ejecutar(lambda: CambiarPropiedad(capitulo, id_elemento, "audio.volumen", volumen))
