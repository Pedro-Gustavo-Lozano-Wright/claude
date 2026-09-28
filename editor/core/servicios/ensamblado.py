"""Unir minutos sin recodificar y agregar las pistas de audio (T10.4).

El video de cada minuto se copia paquete a paquete (sin recodificar) con sus
marcas de tiempo desplazadas; el audio del rango se codifica aparte, en una
sola pasada por idioma, y se intercala minuto a minuto para no acumular
memoria. El MP4 sale con `faststart` (se puede reproducir mientras se descarga).
"""

from __future__ import annotations

import os
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from editor.core.estandar import FOTOGRAMAS_POR_MINUTO, FPS
from editor.core.motor.codificador import IDIOMAS_ISO_639_2, PerfilAudio
from editor.core.motor.mezclador_audio import MUESTRAS_POR_FOTOGRAMA
from editor.core.tareas.cola import Contexto


def unir(
    videos: list[Path],
    audios: list[tuple[np.ndarray, str | None]],
    destino: Path,
    contexto: Contexto,
    perfil_audio: PerfilAudio = PerfilAudio(),
) -> Path:
    """`videos`: un archivo por minuto, en orden. `audios`: (muestras (2, n), idioma) por pista."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{destino.stem}.parcial{destino.suffix}")
    salida = av.open(str(temporal), "w", options={"movflags": "faststart"})
    try:
        with av.open(str(videos[0])) as primero:
            plantilla = primero.streams.video[0]
            stream_video = salida.add_stream_from_template(plantilla)
            base = plantilla.time_base
        streams_audio = []
        for _, idioma in audios:
            stream = salida.add_stream(perfil_audio.codec, rate=perfil_audio.frecuencia)
            stream.layout = "stereo"
            stream.bit_rate = perfil_audio.bitrate
            if idioma:
                stream.metadata["language"] = IDIOMAS_ISO_639_2.get(idioma, idioma)
            streams_audio.append([stream, 0])

        desplazamiento = 0
        muestras_por_minuto = FOTOGRAMAS_POR_MINUTO * MUESTRAS_POR_FOTOGRAMA
        for indice, ruta in enumerate(videos):
            with av.open(str(ruta)) as entrada:
                stream_entrada = entrada.streams.video[0]
                escala = Fraction(stream_entrada.time_base) / Fraction(base)
                maximo = 0
                for paquete in entrada.demux(stream_entrada):
                    if paquete.dts is None:
                        continue
                    pts = round(paquete.pts * escala) if paquete.pts is not None else None
                    dts = round(paquete.dts * escala)
                    duracion = round(paquete.duration * escala) if paquete.duration else 0
                    paquete.pts = None if pts is None else pts + desplazamiento
                    paquete.dts = dts + desplazamiento
                    paquete.stream = stream_video
                    salida.mux(paquete)
                    maximo = max(maximo, (pts if pts is not None else dts) + duracion)
            desplazamiento += max(maximo, round(Fraction(FOTOGRAMAS_POR_MINUTO, FPS) / Fraction(base)))
            for pista, (muestras, _) in enumerate(audios):
                trozo = muestras[:, indice * muestras_por_minuto:(indice + 1) * muestras_por_minuto]
                _codificar_audio(salida, streams_audio[pista], trozo, perfil_audio)
            contexto.progreso(0.5 + 0.5 * (indice + 1) / len(videos), "Ensamblando")
        for stream, _ in streams_audio:
            for paquete in stream.encode():
                salida.mux(paquete)
    finally:
        salida.close()
    os.replace(temporal, destino)
    return destino


def _codificar_audio(salida, estado: list, muestras: np.ndarray, perfil: PerfilAudio) -> None:
    stream, pts = estado
    datos = np.ascontiguousarray(muestras.astype(np.float32))
    tamano = stream.codec_context.frame_size or 1024
    for inicio in range(0, datos.shape[1], tamano):
        trozo = datos[:, inicio:inicio + tamano]
        cuadro = av.AudioFrame.from_ndarray(trozo, format="fltp", layout="stereo")
        cuadro.sample_rate = perfil.frecuencia
        cuadro.pts = pts
        pts += trozo.shape[1]
        for paquete in stream.encode(cuadro):
            salida.mux(paquete)
    estado[1] = pts
