"""Shorts verticales 9:16 (E22).

Cada fotograma se compone directamente a 720×1280 a través de la ventana
vertical del Short (`Compositor.componer(ventana=...)`): la misma calidad que el
video 720p, sin un paso de recorte aparte. El audio y los subtítulos son los del
**primer idioma** del proyecto (en un Short los subtítulos van quemados, porque
se miran casi siempre sin sonido). Sonoridad a −14 LUFS.

El archivo va a `capNNNN/shorts/<nombre del Short>_vNNN.mp4`; el registro de
versión y huella a `_renders.json`, como los minutos.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path

from editor.core.estandar import FPS, Estandar
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto
from editor.core.modelo.short import Short
from editor.core.motor.codificador import Codificador, PerfilAudio
from editor.core.motor.compositor import FINAL, Compositor
from editor.core.motor.decodificador import GestorFuentes
from editor.core.motor.mezclador_audio import Mezclador
from editor.core.proyecto_fs import automatico
from editor.core.proyecto_fs.estado_disco import EstadoDisco
from editor.core.proyecto_fs.gemelo import short_a_datos
from editor.core.proyecto_fs.serializacion import huella
from editor.core.servicios import huellas
from editor.core.servicios.fuentes import ResolutorFuentes
from editor.core.servicios.render import LUFS_YOUTUBE, normalizar, perfil_video
from editor.core.tareas.cola import Contexto
from editor.core.tiempo.nomenclatura import carpeta_shorts

ANCHO_SHORT, ALTO_SHORT = 720, 1280
DURACION_MAXIMA = 180 * FPS      # YouTube acepta Shorts de hasta 3 minutos
DURACION_SUGERIDA = 30 * FPS

SIN_RENDER, AL_DIA, DESACTUALIZADO = "sin render", "al día", "desactualizado"


def idioma_short(proyecto: Proyecto) -> str | None:
    return proyecto.idiomas[0] if proyecto.idiomas else None


def huella_short(capitulo: Capitulo, short: Short, estandar: Estandar, resolutor, idioma: str | None) -> str:
    return huella({
        "short": short_a_datos(short),
        "tamano": [ANCHO_SHORT, ALTO_SHORT],
        "video": [huellas.huella_video_minuto(capitulo, m, estandar, resolutor) for m in short.minutos_cruzados],
        "audio": huellas.huella_audio(capitulo, short.inicio, short.fin, idioma, resolutor),
        "subtitulos": huellas.huella_subtitulos(capitulo, short.inicio, short.fin, idioma),
    })


def estado(proyecto: Proyecto, capitulo: Capitulo, short: Short, resolutor=None) -> str:
    if short.ultimo_render is None:
        return SIN_RENDER
    resolutor = resolutor or ResolutorFuentes.desde(proyecto)
    marca = huella_short(capitulo, short, proyecto.estandar, resolutor, idioma_short(proyecto))
    return AL_DIA if marca == short.ultimo_render.huella else DESACTUALIZADO


def desactualizados(proyecto: Proyecto, numero: int) -> list[str]:
    capitulo = proyecto.capitulo(numero)
    resolutor = ResolutorFuentes.desde(proyecto)
    return [s.id for s in sorted(capitulo.shorts.values(), key=lambda s: s.inicio)
            if estado(proyecto, capitulo, s, resolutor) != AL_DIA]


def ruta_render(raiz: Path, numero: int, short: Short, version: int) -> Path:
    return carpeta_shorts(raiz, numero) / short.nombre_archivo().render(version)


@dataclass
class PedidoShort:
    raiz: Path
    capitulo: Capitulo
    short: Short
    estandar: Estandar
    resolutor: ResolutorFuentes
    idioma: str | None
    version: int
    huella: str

    @classmethod
    def crear(cls, proyecto: Proyecto, numero: int, id_short: str) -> "PedidoShort":
        assert proyecto.raiz is not None
        capitulo = proyecto.capitulo(numero)
        short = capitulo.shorts[id_short]
        resolutor = ResolutorFuentes.desde(proyecto)
        idioma = idioma_short(proyecto)
        version = short.siguiente_version_render
        while ruta_render(proyecto.raiz, numero, short, version).exists():
            version += 1
        return cls(proyecto.raiz, copy.deepcopy(capitulo), copy.deepcopy(short), proyecto.estandar, resolutor,
                   idioma, version, huella_short(capitulo, short, proyecto.estandar, resolutor, idioma))


@dataclass
class ResultadoShort:
    capitulo: int
    id_short: str
    archivo: Path
    version: int
    huella: str


def renderizar(pedido: PedidoShort, contexto: Contexto) -> ResultadoShort:
    """Tarea de fondo."""
    short = pedido.short
    destino = ruta_render(pedido.raiz, pedido.capitulo.numero, short, pedido.version)
    temporal = destino.with_name(f".{destino.stem}.parcial.mp4")
    contexto.progreso(0.0, f"Short {short.nombre}: audio")
    audio = normalizar(Mezclador(pedido.resolutor).mezclar(pedido.capitulo, short.inicio, short.fin, pedido.idioma),
                       LUFS_YOUTUBE)
    fuentes = GestorFuentes()
    compositor = Compositor(fuentes, pedido.resolutor, pedido.raiz / "recursos", FINAL)
    try:
        with Codificador(temporal, ANCHO_SHORT, ALTO_SHORT, perfil_video(pedido.estandar),
                         [(PerfilAudio(), pedido.idioma)]) as salida:
            for f in range(short.inicio, short.fin):
                contexto.comprobar()
                salida.escribir_video(compositor.componer(pedido.capitulo, f, (ANCHO_SHORT, ALTO_SHORT),
                                                          ventana=short.rect_en(f), idioma=pedido.idioma))
                if (f - short.inicio) % 48 == 0:
                    contexto.progreso(0.95 * (f - short.inicio) / short.duracion, f"Short {short.nombre}")
            salida.escribir_audio(audio)
    finally:
        fuentes.cerrar()
    os.replace(temporal, destino)
    contexto.progreso(1.0, "Short listo")
    return ResultadoShort(pedido.capitulo.numero, short.id, destino, pedido.version, pedido.huella)


def registrar(proyecto: Proyecto, estado_disco: EstadoDisco, resultado: ResultadoShort) -> None:
    """Hilo principal: versión y huella del Short en `_renders.json`."""
    automatico.anotar_renders(proyecto, estado_disco, resultado.capitulo,
                              shorts={resultado.id_short: (resultado.version, resultado.huella)})
