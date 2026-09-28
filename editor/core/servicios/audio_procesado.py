"""Procesos de audio que generan un archivo nuevo (E20): reducción de ruido.

El resultado se importa como un Bruto nuevo: el original queda intacto y el
cambio se ve (y se deshace) como cualquier importación.
"""

from __future__ import annotations

from pathlib import Path

import av
import numpy as np

from editor.core.motor.codificador import escribir_wav
from editor.core.motor.mezclador_audio import FRECUENCIA, FuenteAudio
from editor.core.tareas.cola import Contexto

VENTANA = 2048
SALTO = VENTANA // 4


def reducir_ruido(entrada: Path, salida: Path, contexto: Contexto, reduccion_db: float = 15.0,
                  percentil: float = 15.0) -> Path:
    """Puerta espectral: el perfil de ruido es, por frecuencia, el nivel que se supera el
    `percentil`% del tiempo más callado; lo que queda cerca del ruido se atenúa hasta
    `reduccion_db`. Suave en tiempo y frecuencia para no dejar "agua" (artefactos)."""
    with av.open(str(entrada)) as contenedor:
        duracion = (contenedor.duration / av.time_base) if contenedor.duration else 0.0
    muestras = FuenteAudio(entrada).leer(0, int(duracion * FRECUENCIA))
    ventana = np.hanning(VENTANA).astype(np.float32)
    piso = 10 ** (-reduccion_db / 20)
    resultado = np.zeros_like(muestras)
    for c, canal in enumerate(muestras):
        contexto.comprobar()
        cantidad = max(1, 1 + (len(canal) - VENTANA) // SALTO)
        marcos = np.stack([canal[i * SALTO: i * SALTO + VENTANA] for i in range(cantidad)
                           if i * SALTO + VENTANA <= len(canal)]) if len(canal) >= VENTANA else np.zeros((0, VENTANA))
        if len(marcos) == 0:
            resultado[c] = canal
            continue
        espectro = np.fft.rfft(marcos * ventana, axis=1)
        magnitud = np.abs(espectro)
        ruido = np.percentile(magnitud, percentil, axis=0)
        ganancia = np.clip((magnitud - 1.5 * ruido) / np.maximum(magnitud, 1e-9), piso, 1.0)
        # Suavizado: 3 marcos en el tiempo y 3 bins en frecuencia.
        nucleo = np.ones(3) / 3
        ganancia = np.apply_along_axis(lambda g: np.convolve(g, nucleo, mode="same"), 0, ganancia)
        ganancia = np.apply_along_axis(lambda g: np.convolve(g, nucleo, mode="same"), 1, ganancia)
        limpio = np.fft.irfft(espectro * ganancia, n=VENTANA, axis=1) * ventana
        suma = np.zeros(len(canal), dtype=np.float32)
        normal = np.zeros(len(canal), dtype=np.float32)
        for i, marco in enumerate(limpio):
            suma[i * SALTO: i * SALTO + VENTANA] += marco
            normal[i * SALTO: i * SALTO + VENTANA] += ventana ** 2
        normal[normal < 1e-6] = 1.0
        resultado[c] = suma / normal
        contexto.progreso(0.9 * (c + 1) / len(muestras), f"Reduciendo ruido de {entrada.name}")
    salida.parent.mkdir(parents=True, exist_ok=True)
    escribir_wav(salida, np.clip(resultado, -1, 1))
    return salida
