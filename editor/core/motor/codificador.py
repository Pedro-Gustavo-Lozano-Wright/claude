"""Codificación de video y audio con PyAV (T7.7).

- Video a partir de imágenes RGB o RGBA (numpy), a 24 fps exactos.
- Audio a partir de float32 (canales, muestras) a 48 kHz.
- El primer fotograma es siempre clave y los parámetros son idénticos entre
  archivos del mismo perfil: los minutos se pueden unir sin recodificar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from editor.core.estandar import FPS

IDIOMAS_ISO_639_2 = {"es": "spa", "en": "eng", "pt": "por", "fr": "fra", "de": "deu", "it": "ita", "ja": "jpn", "zh": "zho"}


@dataclass(frozen=True)
class PerfilVideo:
    codec: str = "libx264"
    formato_pixel: str = "yuv420p"
    opciones: dict[str, str] = field(default_factory=lambda: {"crf": "18", "preset": "medium"})
    contenedor: str = "mp4"

    @classmethod
    def h264(cls, crf: int, preset: str) -> "PerfilVideo":
        return cls("libx264", "yuv420p", {"crf": str(crf), "preset": preset})

    @classmethod
    def nvenc(cls, calidad: int) -> "PerfilVideo":
        return cls("h264_nvenc", "yuv420p", {"cq": str(calidad), "preset": "p5"})

    @classmethod
    def prores_4444(cls) -> "PerfilVideo":
        return cls("prores_ks", "yuva444p10le", {"profile": "4"}, "mov")

    @property
    def con_alfa(self) -> bool:
        return "a" in self.formato_pixel.replace("yuv", "")


@dataclass(frozen=True)
class PerfilAudio:
    codec: str = "aac"
    bitrate: int = 192_000
    frecuencia: int = 48_000
    canales: int = 2


class Codificador:
    def __init__(
        self,
        ruta: Path,
        ancho: int,
        alto: int,
        video: PerfilVideo | None = PerfilVideo(),
        audios: list[tuple[PerfilAudio, str | None]] | None = None,
    ) -> None:
        """`audios`: una pista por elemento (perfil, idioma ISO 639-1 o None)."""
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta = ruta
        self._contenedor = av.open(str(ruta), "w")
        self._video = None
        if video is not None:
            par = lambda v: v + (v % 2) if "420" in video.formato_pixel else v  # noqa: E731
            self._video = self._contenedor.add_stream(video.codec, rate=FPS)
            self._video.width = par(ancho)
            self._video.height = par(alto)
            self._video.pix_fmt = video.formato_pixel
            self._video.time_base = Fraction(1, FPS)
            self._video.options = dict(video.opciones)
            self._formato_entrada_alfa = video.con_alfa
        self._audios = []
        for perfil, idioma in audios or []:
            stream = self._contenedor.add_stream(perfil.codec, rate=perfil.frecuencia)
            stream.layout = "stereo" if perfil.canales == 2 else "mono"
            if perfil.codec not in ("pcm_s16le", "flac"):
                stream.bit_rate = perfil.bitrate
            if idioma:
                stream.metadata["language"] = IDIOMAS_ISO_639_2.get(idioma, idioma)
            self._audios.append([stream, 0, perfil])
        self._pts_video = 0

    def escribir_video(self, imagen: np.ndarray) -> None:
        assert self._video is not None
        formato = "rgba" if imagen.shape[2] == 4 else "rgb24"
        cuadro = av.VideoFrame.from_ndarray(np.ascontiguousarray(imagen), format=formato)
        if cuadro.width != self._video.width or cuadro.height != self._video.height:
            cuadro = cuadro.reformat(width=self._video.width, height=self._video.height)
        cuadro.pts = self._pts_video
        self._pts_video += 1
        for paquete in self._video.encode(cuadro):
            self._contenedor.mux(paquete)

    def escribir_audio(self, muestras: np.ndarray, pista: int = 0) -> None:
        """`muestras`: float32 (canales, n) en −1…1."""
        stream, pts, perfil = self._audios[pista]
        datos = np.ascontiguousarray(muestras.astype(np.float32))
        tamano_cuadro = stream.codec_context.frame_size or 1024
        for inicio in range(0, datos.shape[1], tamano_cuadro):
            trozo = datos[:, inicio:inicio + tamano_cuadro]
            cuadro = av.AudioFrame.from_ndarray(trozo, format="fltp", layout=stream.layout.name)
            cuadro.sample_rate = perfil.frecuencia
            cuadro.pts = pts
            pts += trozo.shape[1]
            for paquete in stream.encode(cuadro):
                self._contenedor.mux(paquete)
        self._audios[pista][1] = pts

    def cerrar(self) -> None:
        if self._video is not None:
            for paquete in self._video.encode():
                self._contenedor.mux(paquete)
        for stream, _, _ in self._audios:
            for paquete in stream.encode():
                self._contenedor.mux(paquete)
        self._contenedor.close()

    def __enter__(self) -> "Codificador":
        return self

    def __exit__(self, tipo, *_: object) -> None:
        self.cerrar()


def escribir_wav(ruta: Path, muestras: np.ndarray, frecuencia: int = 48_000) -> None:
    """WAV PCM 16 bits (vista previa y audio materializado)."""
    import wave

    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = (np.clip(muestras.T, -1, 1) * 32767).astype("<i2")
    with wave.open(str(ruta), "wb") as archivo:
        archivo.setnchannels(muestras.shape[0])
        archivo.setsampwidth(2)
        archivo.setframerate(frecuencia)
        archivo.writeframes(datos.tobytes())
