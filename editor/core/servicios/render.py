"""Render final: minuto, rango o capítulo, con pistas de idioma.

1. Cada minuto del rango se renderiza (solo video, 1440 fotogramas exactos) y
   se guarda en `.cache/minutos/` con su huella en el nombre. Un minuto cuya
   huella no cambió **no se vuelve a renderizar**.
2. El audio del rango se mezcla en una sola pasada por idioma.
3. Se ensamblan los minutos sin recodificar y se agregan las pistas.
4. Se registra el resultado (estado automático) en el hilo principal.

Idiomas, lo más simple: **un solo video** con una pista de audio por
idioma y, al lado, un `.srt` por idioma con los textos de sus capas T. Los
capítulos de YouTube (marcadores) se escriben en un `.txt` para la descripción.

Perfiles: `VIDEO` (720p del estándar, listo para YouTube) o `SOLO_AUDIO` (`.m4a`).
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path

from editor.core.estandar import FOTOGRAMAS_POR_MINUTO, Estandar
from editor.core.eventos import BusEventos, RenderTerminado
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto
from editor.core.motor.codificador import Codificador, PerfilAudio, PerfilVideo
from editor.core.motor.compositor import FINAL, Compositor
from editor.core.motor.decodificador import GestorFuentes
from editor.core.motor.mezclador_audio import Mezclador
from editor.core.proyecto_fs import automatico
from editor.core.proyecto_fs.estado_disco import EstadoDisco
from editor.core.proyecto_fs.serializacion import huella
from editor.core.servicios import capitulos_youtube, ensamblado, huellas, subtitulos
from editor.core.servicios.fuentes import ResolutorFuentes
from editor.core.tareas.cola import Contexto
from editor.core.tiempo import granularidad
from editor.core.tiempo.nomenclatura import CARPETA_CACHE, NombreRender, carpeta_render, codigo_capitulo, codigo_minuto

VIDEO = "video"
SOLO_AUDIO = "audio"
LUFS_YOUTUBE = -14.0
PERFILES = {VIDEO: "Video 720p (YouTube)", SOLO_AUDIO: "Solo audio (.m4a)"}


@dataclass
class PedidoRender:
    """Instantánea de todo lo que el render necesita (se crea en el hilo principal)."""

    raiz: Path
    capitulo: Capitulo
    estandar: Estandar
    resolutor: ResolutorFuentes
    desde: int | None           # None = capítulo completo
    hasta: int | None
    idiomas: list[str]
    perfil: str = VIDEO
    version: int = 1
    # Sonoridad objetivo (LUFS integrados, p. ej. −14 para YouTube); None = sin normalizar.
    normalizar_lufs: float | None = None

    @classmethod
    def crear(cls, proyecto: Proyecto, numero: int, desde: int | None = None, hasta: int | None = None,
              idiomas: list[str] | None = None, perfil: str = VIDEO,
              normalizar_lufs: float | None = None) -> "PedidoRender":
        assert proyecto.raiz is not None
        capitulo = proyecto.capitulo(numero)
        return cls(
            raiz=proyecto.raiz,
            capitulo=copy.deepcopy(capitulo),
            estandar=proyecto.estandar,
            resolutor=ResolutorFuentes.desde(proyecto),
            desde=desde,
            hasta=hasta if hasta is not None else desde,
            idiomas=list(idiomas or proyecto.idiomas),
            perfil=perfil,
            normalizar_lufs=normalizar_lufs,
            version=_version_libre(proyecto.raiz, capitulo, desde, hasta if hasta is not None else desde),
        )

    @property
    def minutos(self) -> range:
        if self.desde is None:
            return range(len(self.capitulo.minutos))
        return range(self.desde, (self.hasta if self.hasta is not None else self.desde) + 1)


def _version_libre(raiz: Path, capitulo: Capitulo, desde: int | None, hasta: int | None) -> int:
    """Siguiente versión según el registro y, además, sin pisar archivos que ya estén en disco."""
    version = capitulo.siguiente_version(desde, hasta)
    alcance = (desde, hasta if hasta is not None else desde)
    carpeta = carpeta_render(raiz, capitulo.numero)
    if carpeta.exists():
        for archivo in carpeta.iterdir():
            try:
                nombre = NombreRender.desde_archivo(archivo.name)
            except ValueError:
                continue
            if (nombre.desde, nombre.hasta if nombre.hasta is not None else nombre.desde) == alcance:
                version = max(version, nombre.version + 1)
    return version


@dataclass
class ResultadoRender:
    capitulo: int
    archivos: list[Path]
    nombres: list[NombreRender]
    huella: str
    minutos: dict[int, str] = field(default_factory=dict)   # minuto → huella de video renderizada


def perfil_video(estandar: Estandar) -> PerfilVideo:
    render = estandar.render
    if render.aceleracion == "nvenc":
        return PerfilVideo.nvenc(render.crf)
    return PerfilVideo.h264(render.crf, render.preset)


def ruta_minuto_cache(raiz: Path, capitulo: int, minuto: int, huella_video: str) -> Path:
    return raiz / CARPETA_CACHE / "minutos" / f"{codigo_capitulo(capitulo)}_{codigo_minuto(minuto)}_{huella_video}.mp4"


def render_minuto(pedido: PedidoRender, minuto: int, compositor: Compositor, destino: Path, contexto: Contexto,
                  avance: tuple[float, float] = (0.0, 1.0)) -> Path:
    inicio, fin = granularidad.rango_minuto(minuto)
    estandar = pedido.estandar
    temporal = destino.with_name(f".{destino.stem}.parcial.mp4")
    with Codificador(temporal, estandar.lienzo_ancho, estandar.lienzo_alto, perfil_video(estandar)) as salida:
        for f in range(inicio, fin):
            salida.escribir_video(compositor.componer(pedido.capitulo, f, (estandar.lienzo_ancho, estandar.lienzo_alto)))
            if (f - inicio) % 48 == 0:
                contexto.progreso(avance[0] + (avance[1] - avance[0]) * (f - inicio) / FOTOGRAMAS_POR_MINUTO,
                                  f"Minuto {minuto:02d}")
    os.replace(temporal, destino)
    return destino


def renderizar(pedido: PedidoRender, contexto: Contexto) -> ResultadoRender:
    """Tarea de fondo."""
    minutos = list(pedido.minutos)
    videos: list[Path] = []
    huellas_minutos: dict[int, str] = {}
    if pedido.perfil == VIDEO:
        fuentes = GestorFuentes()
        compositor = Compositor(fuentes, pedido.resolutor, pedido.raiz / "recursos", FINAL)
        try:
            for i, minuto in enumerate(minutos):
                contexto.comprobar()
                marca = huellas.huella_video_minuto(pedido.capitulo, minuto, pedido.estandar, pedido.resolutor)
                destino = ruta_minuto_cache(pedido.raiz, pedido.capitulo.numero, minuto, marca)
                if not destino.exists():
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    tramo = (0.5 * i / len(minutos), 0.5 * (i + 1) / len(minutos))
                    render_minuto(pedido, minuto, compositor, destino, contexto, tramo)
                videos.append(destino)
                huellas_minutos[minuto] = marca
        finally:
            fuentes.cerrar()

    inicio = minutos[0] * FOTOGRAMAS_POR_MINUTO
    fin = (minutos[-1] + 1) * FOTOGRAMAS_POR_MINUTO
    mezclador = Mezclador(pedido.resolutor)
    idiomas = pedido.idiomas or [None]  # type: ignore[list-item]
    contexto.progreso(0.5, "Mezclando audio")
    pistas = [(mezclador.mezclar(pedido.capitulo, inicio, fin, idioma), idioma) for idioma in idiomas]
    if pedido.normalizar_lufs is not None:
        contexto.progreso(0.55, "Midiendo sonoridad")
        pistas = [(normalizar(muestras, pedido.normalizar_lufs), idioma) for muestras, idioma in pistas]
    marca_audio = [huellas.huella_audio(pedido.capitulo, inicio, fin, i, pedido.resolutor) for i in idiomas]
    marca_total = huella([pedido.perfil, list(huellas_minutos.items()), marca_audio, pedido.normalizar_lufs])

    carpeta = carpeta_render(pedido.raiz, pedido.capitulo.numero)
    nombre = lambda extension, idioma=None: NombreRender(  # noqa: E731
        pedido.capitulo.numero, pedido.version, pedido.desde, pedido.hasta, extension, idioma)
    archivos: list[Path] = []
    nombres: list[NombreRender] = []
    if pedido.perfil == VIDEO:
        principal = nombre("mp4")
        archivos.append(ensamblado.unir(videos, pistas, carpeta / principal.archivo, contexto))
    else:
        principal = nombre("m4a")
        archivos.append(_solo_audio(pistas, carpeta / principal.archivo))
    nombres.append(principal)
    # Acompañan al entregable: un `.srt` por idioma con subtítulos y los capítulos de YouTube.
    for idioma in pedido.idiomas:
        texto = subtitulos.srt_de_idioma(pedido.capitulo, idioma, inicio, fin)
        if texto:
            extra = nombre("srt", idioma)
            (carpeta / extra.archivo).write_text(texto, encoding="utf-8")
            archivos.append(carpeta / extra.archivo)
            nombres.append(extra)
    marcas, _ = capitulos_youtube.capitulos(pedido.capitulo, inicio, fin)
    if marcas:
        extra = nombre("txt")
        (carpeta / extra.archivo).write_text(marcas + "\n", encoding="utf-8")
        archivos.append(carpeta / extra.archivo)
        nombres.append(extra)
    contexto.progreso(1.0, "Render terminado")
    return ResultadoRender(pedido.capitulo.numero, archivos, nombres, marca_total, huellas_minutos)


def _solo_audio(pistas, destino: Path) -> Path:
    temporal = destino.with_name(f".{destino.stem}.parcial{destino.suffix}")
    with Codificador(temporal, 0, 0, None, [(PerfilAudio(), idioma) for _, idioma in pistas]) as salida:
        for indice, (muestras, _) in enumerate(pistas):
            salida.escribir_audio(muestras, indice)
    os.replace(temporal, destino)
    return destino


def normalizar(muestras, objetivo: float):
    """Ganancia para llegar a `objetivo` LUFS sin pasar de −1 dBFS de pico; luego el limitador."""
    from editor.core.motor.mezclador_audio import limitar
    from editor.core.servicios import analisis

    lufs, pico = analisis.sonoridad(muestras)
    ganancia = analisis.ganancia_para(lufs, objetivo, pico)
    if ganancia == 0:
        return muestras
    return limitar(muestras * (10 ** (ganancia / 20)))


def registrar(proyecto: Proyecto, estado: EstadoDisco, resultado: ResultadoRender, bus: BusEventos | None = None) -> None:
    """Hilo principal: estado automático del render (no depende de que el usuario guarde)."""
    automatico.anotar_renders(proyecto, estado, resultado.capitulo,
                              entregables=[(n.archivo, resultado.huella) for n in resultado.nombres],
                              minutos=resultado.minutos)
    if bus is not None:
        for archivo in resultado.archivos:
            bus.publicar(RenderTerminado(f"render-{resultado.capitulo}", str(archivo), True))
