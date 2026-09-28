"""Análisis de medios para el Taller (E17): escenas, silencios y sincronía de audio.

Todo corre en tareas de fondo y devuelve datos simples; nada toca el modelo.

- `detectar_escenas`: cortes de plano de un video, en **fotogramas nativos**.
- `detectar_silencios`: tramos en silencio de un archivo con audio, en segundos.
- `desfase`: cuánto está adelantado un audio externo respecto de una referencia
  (correlación cruzada de envolventes a 1 kHz, con FFT).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np

from editor.core.motor.mezclador_audio import FRECUENCIA, FuenteAudio
from editor.core.tareas.cola import Contexto

ANCHO_ANALISIS, ALTO_ANALISIS = 64, 36
FRECUENCIA_ENVOLVENTE = 1000


def detectar_escenas(ruta: Path, contexto: Contexto, sensibilidad: float = 3.0, minimo: float = 0.08) -> list[int]:
    """Fotogramas nativos donde empieza un plano nuevo (sin contar el 0).

    Diferencia media de luminancia entre fotogramas vecinos a 64×36; un corte es
    un pico mayor que `sensibilidad` desviaciones sobre la media y que `minimo`.
    """
    diferencias: list[float] = []
    anterior: np.ndarray | None = None
    with av.open(str(ruta)) as contenedor:
        if not contenedor.streams.video:
            return []
        flujo = contenedor.streams.video[0]
        flujo.thread_type = "AUTO"
        total = flujo.frames or 0
        for indice, cuadro in enumerate(contenedor.decode(flujo)):
            gris = cuadro.reformat(width=ANCHO_ANALISIS, height=ALTO_ANALISIS, format="gray").to_ndarray()
            gris = gris.astype(np.float32) / 255.0
            diferencias.append(0.0 if anterior is None else float(np.abs(gris - anterior).mean()))
            anterior = gris
            if indice % 240 == 0:
                contexto.comprobar()
                if total:
                    contexto.progreso(min(0.99, indice / total), f"Buscando escenas en {ruta.name}")
    if len(diferencias) < 3:
        return []
    valores = np.array(diferencias[1:])
    umbral = max(minimo, float(valores.mean() + sensibilidad * valores.std()))
    cortes = [i for i, d in enumerate(diferencias) if i > 0 and d >= umbral]
    # Un corte cada medio segundo como mucho (los fundidos dan varios picos seguidos).
    filtrados: list[int] = []
    for corte in cortes:
        if not filtrados or corte - filtrados[-1] > 12:
            filtrados.append(corte)
    return filtrados


@dataclass(frozen=True)
class Silencio:
    inicio: float   # segundos
    fin: float


def _mono(ruta: Path, contexto: Contexto | None = None) -> np.ndarray:
    fuente = FuenteAudio(ruta)
    if not fuente.tiene_audio:
        return np.zeros(0, dtype=np.float32)
    with av.open(str(ruta)) as contenedor:
        duracion = (contenedor.duration / av.time_base) if contenedor.duration else 0.0
    total = int(duracion * FRECUENCIA)
    bloques = []
    paso = FRECUENCIA * 30
    for desde in range(0, total, paso):
        if contexto is not None:
            contexto.comprobar()
            contexto.progreso(0.8 * desde / max(1, total), f"Leyendo audio de {ruta.name}")
        bloques.append(fuente.leer(desde, min(paso, total - desde)).mean(axis=0))
    return np.concatenate(bloques) if bloques else np.zeros(0, dtype=np.float32)


def detectar_silencios(ruta: Path, contexto: Contexto, umbral_db: float = -40.0,
                       duracion_minima: float = 0.5) -> list[Silencio]:
    """Tramos con nivel RMS por debajo de `umbral_db` (dBFS) durante al menos `duracion_minima` s."""
    muestras = _mono(ruta, contexto)
    ventana = FRECUENCIA // 20                          # 50 ms
    cantidad = len(muestras) // ventana
    if cantidad == 0:
        return []
    rms = np.sqrt(np.mean(muestras[:cantidad * ventana].reshape(cantidad, ventana) ** 2, axis=1) + 1e-12)
    silencio = 20 * np.log10(rms) < umbral_db
    tramos: list[Silencio] = []
    inicio: int | None = None
    for i, callado in enumerate(np.append(silencio, False)):
        if callado and inicio is None:
            inicio = i
        elif not callado and inicio is not None:
            if (i - inicio) * 0.05 >= duracion_minima:
                tramos.append(Silencio(round(inicio * 0.05, 2), round(i * 0.05, 2)))
            inicio = None
    return tramos


def envolvente(muestras: np.ndarray) -> np.ndarray:
    """Mono 48 kHz → envolvente a 1 kHz sin componente continua (robusta a ganancias distintas)."""
    paso = FRECUENCIA // FRECUENCIA_ENVOLVENTE
    cantidad = len(muestras) // paso
    if cantidad == 0:
        return np.zeros(0, dtype=np.float32)
    bloques = np.abs(muestras[:cantidad * paso]).reshape(cantidad, paso).mean(axis=1)
    bloques = bloques - bloques.mean()
    norma = np.linalg.norm(bloques)
    return (bloques / norma) if norma > 0 else bloques


def desfase(referencia: np.ndarray, externo: np.ndarray) -> tuple[float, float]:
    """(segundos, confianza 0–1). Positivo: el sonido de la referencia en t está en el externo en t + desfase."""
    a, b = envolvente(referencia), envolvente(externo)
    if len(a) == 0 or len(b) == 0:
        return 0.0, 0.0
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    correlacion = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    retraso = int(np.argmax(correlacion))
    if retraso > n // 2:
        retraso -= n
    confianza = float(max(0.0, min(1.0, correlacion.max())))
    return retraso / FRECUENCIA_ENVOLVENTE, confianza


def desfase_con_archivo(referencia: np.ndarray, ruta_externa: Path, contexto: Contexto) -> tuple[float, float]:
    """`referencia`: estéreo o mono a 48 kHz (p. ej. la mezcla del Elemento de la timeline)."""
    mono = referencia.mean(axis=0) if referencia.ndim == 2 else referencia
    externo = _mono(ruta_externa, contexto)
    contexto.progreso(0.9, "Comparando audio")
    return desfase(mono, externo)
