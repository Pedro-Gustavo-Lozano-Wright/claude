"""Importar archivos al proyecto (T9.3).

Flujo (PROJECT.md, 22.5):
1. Hilo principal: `preparar_bruto` reserva ID y número y decide el tipo.
2. Tarea de fondo: `copiar_y_analizar` copia a `brutos/` (comprobando espacio)
   y analiza: tamaño, fps declarado, fps **medido** por marcas de tiempo, fps
   variable, alfa, audio y duración.
3. Hilo principal: comando `AgregarBruto` + evento `BrutoImportado`.

Si el usuario no guarda, el archivo queda en `brutos/` y el escáner lo informa
como "sin registrar".
"""

from __future__ import annotations

import shutil
import statistics
from fractions import Fraction
from pathlib import Path

import av
from PIL import Image

from editor.core.estandar import FPS
from editor.core.modelo.bruto import Bruto, TipoMedio
from editor.core.modelo.proyecto import Proyecto
from editor.core.motor.decodificador import EXTENSIONES_IMAGEN, tiene_alfa
from editor.core.proyecto_fs import estructura
from editor.core.tareas.cola import Contexto
from editor.core.tiempo.granularidad import normalizar_fps
from editor.core.tiempo.nomenclatura import normalizar_extension, normalizar_nombre

EXTENSIONES_AUDIO = {"wav", "mp3", "aac", "m4a", "flac", "ogg", "opus", "aiff", "aif"}
PAQUETES_PARA_MEDIR = 600
TOLERANCIA_VFR = 0.02


class EspacioInsuficiente(OSError):
    pass


def tipo_de(ruta: Path) -> TipoMedio:
    extension = normalizar_extension(ruta.suffix)
    if extension in EXTENSIONES_IMAGEN:
        return TipoMedio.IMAGEN
    if extension in EXTENSIONES_AUDIO:
        return TipoMedio.AUDIO
    return TipoMedio.VIDEO


def preparar_bruto(proyecto: Proyecto, origen: Path, nombre: str | None = None) -> Bruto:
    """Hilo principal: reserva ID y número (el modelo no se modifica todavía)."""
    return Bruto(
        id=proyecto.nuevo_id(),
        numero=proyecto.taller.siguiente_numero_bruto(),
        nombre=normalizar_nombre(nombre or origen.stem),
        tipo=tipo_de(origen),
        extension=normalizar_extension(origen.suffix),
        origen=str(origen),
    )


def copiar_y_analizar(raiz: Path, bruto: Bruto, origen: Path, contexto: Contexto) -> Bruto:
    """Tarea de fondo: copia el archivo a `brutos/` y completa el análisis del Bruto."""
    destino = estructura.ruta_bruto(raiz, bruto)
    tamano = origen.stat().st_size
    libre = shutil.disk_usage(raiz).free
    if libre < tamano * 1.1:
        raise EspacioInsuficiente(f"Faltan {(tamano * 1.1 - libre) / 1e9:.1f} GB para importar {origen.name}.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    copiado = 0
    with origen.open("rb") as entrada, parcial.open("wb") as salida:
        while bloque := entrada.read(8 * 1024 * 1024):
            salida.write(bloque)
            copiado += len(bloque)
            contexto.progreso(0.9 * copiado / max(1, tamano), f"Copiando {origen.name}")
    parcial.replace(destino)
    analizar(destino, bruto)
    bruto.archivo = destino
    contexto.progreso(1.0, f"{origen.name} importado")
    return bruto


def analizar(ruta: Path, bruto: Bruto) -> Bruto:
    if bruto.tipo is TipoMedio.IMAGEN:
        with Image.open(ruta) as imagen:
            bruto.ancho, bruto.alto = imagen.size
            bruto.tiene_alfa = "A" in imagen.mode or "transparency" in imagen.info
            bruto.fotogramas_nativos = 1
        return bruto
    with av.open(str(ruta)) as contenedor:
        duracion = contenedor.duration / av.time_base if contenedor.duration else 0.0
        if contenedor.streams.audio:
            audio = contenedor.streams.audio[0]
            bruto.tiene_audio = True
            bruto.audio_frecuencia = audio.codec_context.sample_rate or 0
        if bruto.tipo is TipoMedio.AUDIO or not contenedor.streams.video:
            bruto.tipo = TipoMedio.AUDIO if not contenedor.streams.video else bruto.tipo
            bruto.fps_detectado = Fraction(FPS)
            bruto.fotogramas_nativos = max(1, round(duracion * FPS))
            return bruto
        video = contenedor.streams.video[0]
        codec = video.codec_context
        bruto.ancho, bruto.alto = codec.width, codec.height
        bruto.tiene_alfa = tiene_alfa(codec.pix_fmt)
        declarado = video.average_rate or video.guessed_rate
        bruto.fps_detectado = normalizar_fps(Fraction(declarado)) if declarado else None
        bruto.fps_medido, bruto.vfr = _medir_fps(contenedor, video)
        fps = bruto.fps_medido or bruto.fps_detectado or Fraction(FPS)
        bruto.fotogramas_nativos = video.frames or max(1, round(duracion * float(fps)))
    return bruto


def _medir_fps(contenedor, video) -> tuple[Fraction | None, bool]:
    """fps a partir de las marcas de tiempo reales de los primeros paquetes (sin decodificar)."""
    marcas = []
    for paquete in contenedor.demux(video):
        if paquete.pts is not None:
            marcas.append(paquete.pts)
        if len(marcas) >= PAQUETES_PARA_MEDIR:
            break
    marcas = sorted(set(marcas))
    if len(marcas) < 3 or video.time_base is None:
        return None, False
    pasos = [b - a for a, b in zip(marcas, marcas[1:])]
    mediana = statistics.median(pasos)
    if mediana <= 0:
        return None, False
    fps = normalizar_fps(1 / (Fraction(mediana) * video.time_base))
    pasos.sort()
    extremo_bajo = pasos[len(pasos) // 20]
    extremo_alto = pasos[-(len(pasos) // 20) - 1]
    vfr = (extremo_alto - extremo_bajo) / mediana > TOLERANCIA_VFR
    return fps, vfr
