"""Cambiar la duración del audio sin cambiar el tono: WSOLA.

Se corta la señal en ventanas solapadas; cada ventana se toma de la posición de
entrada que le corresponde (± una tolerancia) donde mejor continúa la anterior,
y se suman con ventana de Hann. Es rápido en numpy y suena bien con voz y
música entre 0,5× y 2×. Fuera de ese rango se usa el remuestreo simple.
"""

from __future__ import annotations

import numpy as np

VENTANA = 1024          # ~21 ms a 48 kHz
SALTO = VENTANA // 2
TOLERANCIA = 256
FACTOR_MINIMO, FACTOR_MAXIMO = 0.5, 2.0


def remuestrear(muestras: np.ndarray, largo: int) -> np.ndarray:
    """Cambio de largo por interpolación (cambia el tono)."""
    if muestras.shape[1] == largo:
        return muestras
    if muestras.shape[1] == 0 or largo <= 0:
        return np.zeros((muestras.shape[0], max(0, largo)), dtype=np.float32)
    posiciones = np.linspace(0, muestras.shape[1] - 1, largo)
    indices = np.arange(muestras.shape[1])
    return np.vstack([np.interp(posiciones, indices, canal) for canal in muestras]).astype(np.float32)


def estirar(muestras: np.ndarray, largo: int) -> np.ndarray:
    """Devuelve `largo` muestras con el mismo contenido y el mismo tono (canales × muestras)."""
    entrada = muestras.shape[1]
    if entrada == largo:
        return muestras.astype(np.float32, copy=False)
    if entrada < VENTANA * 2 or largo < VENTANA * 2:
        return remuestrear(muestras, largo)
    factor = largo / entrada                       # >1 alarga (más lento)
    if not FACTOR_MINIMO <= factor <= FACTOR_MAXIMO:
        return remuestrear(muestras, largo)
    canales = muestras.shape[0]
    mono = muestras.mean(axis=0)
    hann = np.hanning(VENTANA).astype(np.float32)
    salida = np.zeros((canales, largo + VENTANA), dtype=np.float32)
    peso = np.zeros(largo + VENTANA, dtype=np.float32)
    anterior = 0                                   # dónde terminó (en la entrada) la ventana anterior
    for destino in range(0, largo, SALTO):
        ideal = int(destino / factor)
        if destino == 0:
            origen = 0
        else:
            # La mejor continuación de lo ya escrito dentro de ±TOLERANCIA de la posición ideal.
            referencia = mono[anterior + SALTO: anterior + SALTO + SALTO]
            desde = max(0, ideal - TOLERANCIA)
            hasta = min(entrada - VENTANA, ideal + TOLERANCIA)
            if hasta <= desde or len(referencia) < SALTO:
                origen = min(max(0, ideal), entrada - VENTANA)
            else:
                zona = mono[desde: hasta + SALTO]
                correlacion = np.correlate(zona, referencia, mode="valid")
                origen = desde + int(np.argmax(correlacion))
        origen = min(max(0, origen), entrada - VENTANA)
        salida[:, destino: destino + VENTANA] += muestras[:, origen: origen + VENTANA] * hann
        peso[destino: destino + VENTANA] += hann
        anterior = origen
    peso[peso < 1e-3] = 1.0
    return (salida[:, :largo] / peso[:largo]).astype(np.float32)
