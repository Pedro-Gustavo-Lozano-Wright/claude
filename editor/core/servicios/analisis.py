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


# --- E19: movimiento de cámara para estabilizar -------------------------------------------

def movimiento(ruta: Path, desde: int, hasta: int, contexto: Contexto, suavizado: int = 15) -> dict[int, tuple[float, float, float]]:
    """Corrección por fotograma [desde, hasta) del archivo (24 fps): (dx, dy, grados) que la anulan.

    Sigue puntos con Lucas-Kanade, estima una transformación rígida por par de
    fotogramas, acumula la trayectoria y la suaviza con una media móvil; la
    corrección es suavizada − real. Claves: fotograma relativo a `desde`.
    """
    import cv2

    from editor.core.motor.decodificador import FuenteVideo

    fuente = FuenteVideo(ruta)
    try:
        escala = min(1.0, 480 / max(1, fuente.info.ancho))
        tamano = (max(16, round(fuente.info.ancho * escala)), max(16, round(fuente.info.alto * escala)))
        anterior = None
        trayectoria = [(0.0, 0.0, 0.0)]
        for n in range(desde, hasta):
            if (n - desde) % 24 == 0:
                contexto.comprobar()
                contexto.progreso(0.9 * (n - desde) / max(1, hasta - desde), "Midiendo el movimiento")
            gris = cv2.cvtColor(fuente.fotograma(n, tamano)[..., :3], cv2.COLOR_RGB2GRAY)
            if anterior is not None:
                dx = dy = da = 0.0
                puntos = cv2.goodFeaturesToTrack(anterior, maxCorners=200, qualityLevel=0.01, minDistance=20)
                if puntos is not None and len(puntos) >= 6:
                    siguientes, estado, _ = cv2.calcOpticalFlowPyrLK(anterior, gris, puntos, None)
                    buenos = estado.reshape(-1) == 1
                    if buenos.sum() >= 6:
                        matriz, _ = cv2.estimateAffinePartial2D(puntos[buenos], siguientes[buenos])
                        if matriz is not None:
                            dx, dy = float(matriz[0, 2]), float(matriz[1, 2])
                            da = float(np.degrees(np.arctan2(matriz[1, 0], matriz[0, 0])))
                x, y, a = trayectoria[-1]
                trayectoria.append((x + dx / escala, y + dy / escala, a + da))
            anterior = gris
    finally:
        fuente.cerrar()
    real = np.array(trayectoria)
    ventana = max(1, suavizado)
    relleno = np.pad(real, ((ventana, ventana), (0, 0)), mode="edge")
    nucleo = np.ones(2 * ventana + 1) / (2 * ventana + 1)
    suave = np.stack([np.convolve(relleno[:, c], nucleo, mode="valid") for c in range(3)], axis=1)
    correccion = suave - real
    return {k: (float(c[0]), float(c[1]), float(c[2])) for k, c in enumerate(correccion)}


# --- E20: sonoridad (ITU-R BS.1770 / EBU R128) ---------------------------------------------

# Coeficientes del filtro K de BS.1770-4 a 48 kHz: (b0, b1, b2, a1, a2).
_ESTANTE = (1.53512485958697, -2.69169618940638, 1.19839281085285, -1.69065929318241, 0.73248077421585)
_PASO_ALTO = (1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621)


def _respuesta_k(bins: int, frecuencia: int) -> np.ndarray:
    """|H(f)|² del filtro K en las frecuencias de una rfft de `bins` puntos."""
    f = np.fft.rfftfreq(bins, 1 / frecuencia)
    z = np.exp(-2j * np.pi * f / frecuencia)
    respuesta = np.ones_like(z)
    for b0, b1, b2, a1, a2 in (_ESTANTE, _PASO_ALTO):
        respuesta *= (b0 + b1 * z + b2 * z * z) / (1 + a1 * z + a2 * z * z)
    return np.abs(respuesta) ** 2


def sonoridad(muestras: np.ndarray, frecuencia: int = FRECUENCIA) -> tuple[float, float]:
    """(LUFS integrados, pico en dBFS) de una señal estéreo (2, n).

    Bloques de 400 ms con 75 % de solape, puertas absoluta (−70) y relativa (−10 LU).
    La ponderación K se aplica sobre el espectro de cada bloque (Parseval): la energía
    por bloque es lo único que usa la medida, así que no hace falta filtrar en el tiempo.
    """
    if muestras.size == 0:
        return float("-inf"), float("-inf")
    bloque, salto = int(0.4 * frecuencia), int(0.1 * frecuencia)
    n = muestras.shape[1]
    if n < bloque:
        bloque = salto = n
    peso = _respuesta_k(bloque, frecuencia)
    peso[1:-1] *= 2                                          # bins que representan ±f
    inicios = np.arange(0, n - bloque + 1, salto)
    energias = np.zeros(len(inicios))
    for canal in muestras:
        # Por tandas para no crear una matriz enorme con un capítulo entero.
        for i in range(0, len(inicios), 512):
            tanda = inicios[i: i + 512]
            marcos = np.stack([canal[k: k + bloque] for k in tanda]).astype(np.float64)
            espectro = np.abs(np.fft.rfft(marcos, axis=1)) ** 2
            energias[i: i + 512] += (espectro * peso).sum(axis=1) / (bloque * bloque)
    con_senal = energias[energias > 10 ** ((-70 + 0.691) / 10)]              # puerta absoluta −70 LUFS
    if con_senal.size == 0:
        return float("-inf"), _pico(muestras)
    relativa = -0.691 + 10 * np.log10(np.mean(con_senal)) - 10              # puerta relativa −10 LU
    finales = con_senal[-0.691 + 10 * np.log10(con_senal) > relativa]
    lufs = -0.691 + 10 * np.log10(np.mean(finales if finales.size else con_senal))
    return float(lufs), _pico(muestras)


def _pico(muestras: np.ndarray) -> float:
    maximo = float(np.max(np.abs(muestras))) if muestras.size else 0.0
    return float(20 * np.log10(maximo)) if maximo > 0 else float("-inf")


def ganancia_para(lufs_medidos: float, objetivo: float = -14.0, pico_db: float = 0.0, techo_db: float = -1.0) -> float:
    """dB a aplicar para llegar al objetivo sin que el pico pase del techo."""
    if lufs_medidos == float("-inf"):
        return 0.0
    ganancia = objetivo - lufs_medidos
    if pico_db != float("-inf"):
        ganancia = min(ganancia, techo_db - pico_db)
    return round(ganancia, 2)


# --- E20: voz para bajar la música (ducking) -------------------------------------------------

def actividad(muestras: np.ndarray, umbral_db: float = -38.0, ventana_s: float = 0.05,
              retencion_s: float = 0.4) -> np.ndarray:
    """Por ventana de 50 ms: True donde hay voz (RMS sobre el umbral), con retención para no cortar."""
    mono = muestras.mean(axis=0) if muestras.ndim == 2 else muestras
    ventana = int(FRECUENCIA * ventana_s)
    cantidad = len(mono) // ventana
    if cantidad == 0:
        return np.zeros(0, dtype=bool)
    rms = np.sqrt(np.mean(mono[:cantidad * ventana].reshape(cantidad, ventana) ** 2, axis=1) + 1e-12)
    activo = 20 * np.log10(rms) > umbral_db
    retencion = int(retencion_s / ventana_s)
    resultado = activo.copy()
    ultimo = -10**9
    for i, a in enumerate(activo):
        if a:
            ultimo = i
        elif i - ultimo <= retencion:
            resultado[i] = True
    return resultado


def tramos_activos(activo: np.ndarray, ventana_s: float = 0.05) -> list[tuple[float, float]]:
    """Ventanas activas → tramos (inicio, fin) en segundos."""
    tramos: list[tuple[float, float]] = []
    inicio = None
    for i, a in enumerate(np.append(activo, False)):
        if a and inicio is None:
            inicio = i
        elif not a and inicio is not None:
            tramos.append((inicio * ventana_s, i * ventana_s))
            inicio = None
    return tramos
