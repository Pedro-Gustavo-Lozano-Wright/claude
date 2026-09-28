"""Vista previa en 4 niveles con el audio como reloj maestro.

| Nivel | Uso | Fuente de píxeles | Salida |
|---|---|---|---|
| 1–2 | Scrubbing y edición en vivo | Banco (256×144, 10 fps) | JPEG en bytes para `ft.Image(src=…)` |
| 3 | Reproducción fluida | Pre-render del minuto 960×540 con audio | `.mp4` para `flet_video.Video` |
| 4 | Pausa | Archivos reales, calidad final | JPEG en bytes |

El núcleo no conoce Flet: entrega bytes y rutas. `RelojAudio` compensa que
`Audio.get_current_position()` sea asíncrono y tenga latencia.
"""

from __future__ import annotations

import copy
import os
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from editor.core.estandar import FOTOGRAMAS_POR_MINUTO, FPS, Estandar
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto
from editor.core.motor.codificador import Codificador, PerfilAudio, PerfilVideo, escribir_wav
from editor.core.motor.compositor import FINAL, VISTA_PREVIA, Compositor
from editor.core.motor.decodificador import GestorFuentes
from editor.core.motor.mezclador_audio import Mezclador
from editor.core.servicios import huellas
from editor.core.servicios.banco import GestorFuentesBanco
from editor.core.servicios.fuentes import ResolutorFuentes
from editor.core.tareas.cola import Contexto
from editor.core.tiempo import granularidad
from editor.core.tiempo.nomenclatura import CARPETA_CACHE, codigo_capitulo, codigo_minuto


def a_jpeg(imagen: np.ndarray, calidad: int) -> bytes:
    correcto, datos = cv2.imencode(".jpg", cv2.cvtColor(imagen, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, calidad])
    if not correcto:
        raise RuntimeError("No se pudo codificar el JPEG de vista previa.")
    return datos.tobytes()


class ServicioVistaPrevia:
    """Se crea al abrir el proyecto. Los métodos de niveles 1, 2 y 4 son rápidos y se
    pueden llamar desde la tarea del monitor (prioridad 1); los de nivel 3 y audio son
    tareas más largas."""

    def __init__(self, proyecto: Proyecto, calidad_jpeg: int = 80, calidad_pausa: int = 90, cache_mb: int = 512) -> None:
        assert proyecto.raiz is not None
        self.raiz = proyecto.raiz
        self.estandar: Estandar = proyecto.estandar
        self.calidad_jpeg = calidad_jpeg
        self.calidad_pausa = calidad_pausa
        self.resolutor = ResolutorFuentes.desde(proyecto)
        recursos = self.raiz / "recursos"
        self._banco = GestorFuentesBanco(self.raiz)
        self._real = GestorFuentes()
        self._rapido = Compositor(self._banco, self.resolutor, recursos, VISTA_PREVIA)
        self._exacto = Compositor(self._real, self.resolutor, recursos, FINAL)
        self._mezclador = Mezclador(self.resolutor)

    def actualizar_taller(self, proyecto: Proyecto) -> None:
        """Tras importar u hornear: el resolutor necesita la copia nueva del Taller."""
        self.resolutor.taller = copy.deepcopy(proyecto.taller)

    def olvidar(self, ruta: Path | None = None) -> None:
        """Cierra archivos (antes de guardar o tras reemplazarlos)."""
        self._banco.cerrar(ruta)
        self._real.cerrar(ruta)
        self._mezclador.olvidar(ruta)

    # --- Niveles 1, 2 y 4 --------------------------------------------------------------

    def fotograma_rapido(self, capitulo: Capitulo, f: int, tamano: tuple[int, int], idioma: str | None = None) -> bytes:
        return a_jpeg(self._rapido.componer(capitulo, f, tamano, idioma=idioma), self.calidad_jpeg)

    def fotograma_exacto(self, capitulo: Capitulo, f: int, tamano: tuple[int, int], idioma: str | None = None) -> bytes:
        return a_jpeg(self._exacto.componer(capitulo, f, tamano, idioma=idioma), self.calidad_pausa)

    def fotograma_ventana(self, capitulo: Capitulo, f: int, tamano: tuple[int, int], ventana,
                          idioma: str | None = None) -> bytes:
        """Vista previa de un Short: el fotograma visto a través de su ventana vertical."""
        return a_jpeg(self._rapido.componer(capitulo, f, tamano, ventana=ventana, idioma=idioma), self.calidad_jpeg)

    def imagen_exacta(self, capitulo: Capitulo, f: int, tamano: tuple[int, int], idioma: str | None = None):
        """RGB uint8 sin comprimir (para los monitores de señal)."""
        return self._exacto.componer(capitulo, f, tamano, idioma=idioma)

    # --- Audio -----------------------------------------------------------------------------

    def audio(self, capitulo: Capitulo, inicio: int, fin: int, idioma: str | None, contexto: Contexto) -> Path:
        """WAV de vista previa de un rango, en caché por huella."""
        marca = huellas.huella_audio(capitulo, inicio, fin, idioma, self.resolutor)
        destino = self.raiz / CARPETA_CACHE / "audio" / f"{codigo_capitulo(capitulo.numero)}_{inicio}_{fin}_{marca}.wav"
        if not destino.exists():
            contexto.progreso(0.1, "Mezclando audio")
            temporal = destino.with_name(f".{destino.stem}.parcial.wav")
            escribir_wav(temporal, self._mezclador.mezclar(capitulo, inicio, fin, idioma))
            os.replace(temporal, destino)
        contexto.progreso(1.0, "Audio listo")
        return destino

    # --- Nivel 3 ---------------------------------------------------------------------------

    def ruta_prerender(self, capitulo: Capitulo, minuto: int, idioma: str | None) -> Path:
        marca = huellas.huella_minuto(capitulo, minuto, self.estandar, self.resolutor, idioma)
        nombre = f"{codigo_capitulo(capitulo.numero)}_{codigo_minuto(minuto)}_{marca}.mp4"
        return self.raiz / CARPETA_CACHE / "prerender" / nombre

    def prerender_minuto(self, capitulo: Capitulo, minuto: int, idioma: str | None, contexto: Contexto) -> Path:
        """Tarea de fondo (prioridad 3 o 5). `capitulo` debe ser una instantánea."""
        destino = self.ruta_prerender(capitulo, minuto, idioma)
        if destino.exists():
            return destino
        parametros = self.estandar.prerender
        tamano = (parametros.ancho, parametros.alto)
        inicio, fin = granularidad.rango_minuto(minuto)
        temporal = destino.with_name(f".{destino.stem}.parcial.mp4")
        perfil = PerfilVideo(parametros.codec_video, "yuv420p", {"crf": str(parametros.crf), "preset": parametros.preset})
        muestras = self._mezclador.mezclar(capitulo, inicio, fin, idioma)
        with Codificador(temporal, *tamano, perfil, [(PerfilAudio(), idioma)]) as salida:
            for f in range(inicio, fin):
                salida.escribir_video(self._rapido.componer(capitulo, f, tamano, idioma=idioma))
                if (f - inicio) % 48 == 0:
                    contexto.progreso((f - inicio) / FOTOGRAMAS_POR_MINUTO, f"Vista previa del minuto {minuto:02d}")
            salida.escribir_audio(muestras)
        os.replace(temporal, destino)
        return destino

    def minutos_listos(self, capitulo: Capitulo, idioma: str | None) -> dict[int, bool]:
        """Para la barra verde/roja del mapa."""
        return {m: self.ruta_prerender(capitulo, m, idioma).exists() for m in range(len(capitulo.minutos))}


@dataclass
class RelojAudio:
    """Posición del reproductor de audio estimada entre consultas.

    `sincronizar` se llama con cada respuesta de `get_current_position()`;
    `fotograma()` extrapola con el reloj monotónico mientras tanto.
    """

    fotograma_base: int = 0
    _segundos_audio: float = 0.0
    _momento: float = 0.0
    reproduciendo: bool = False

    def sincronizar(self, segundos_audio: float, reproduciendo: bool = True) -> None:
        self._segundos_audio = segundos_audio
        self._momento = time.monotonic()
        self.reproduciendo = reproduciendo

    def fotograma(self) -> int:
        segundos = self._segundos_audio
        if self.reproduciendo:
            segundos += time.monotonic() - self._momento
        return self.fotograma_base + int(segundos * FPS)
