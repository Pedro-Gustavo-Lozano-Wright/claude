"""Forma de onda: picos de audio por fotograma para dibujar en la timeline (T9.6).

Un valor por fotograma (2000 muestras) y canal, entre 0 y 1, en
`.cache/ondas/<clave>.json`. La clave es la misma que la del banco.
"""

from __future__ import annotations

import json
from pathlib import Path

import av
import numpy as np

from editor.core.motor.mezclador_audio import FRECUENCIA, MUESTRAS_POR_FOTOGRAMA, FuenteAudio
from editor.core.servicios.banco import clave
from editor.core.tareas.cola import Contexto
from editor.core.tiempo.nomenclatura import CARPETA_CACHE


def ruta_onda(raiz: Path, ruta: Path) -> Path:
    return raiz / CARPETA_CACHE / "ondas" / f"{clave(ruta)}.json"


def generar(raiz: Path, ruta: Path, contexto: Contexto) -> Path | None:
    destino = ruta_onda(raiz, ruta)
    if destino.exists():
        return destino
    with av.open(str(ruta)) as contenedor:
        if not contenedor.streams.audio:
            return None
        duracion = contenedor.duration / av.time_base if contenedor.duration else 0.0
    fuente = FuenteAudio(ruta)
    fotogramas = max(1, int(duracion * FRECUENCIA) // MUESTRAS_POR_FOTOGRAMA)
    picos: list[list[float]] = []
    paso = 24 * 10  # 10 s por lectura
    for inicio in range(0, fotogramas, paso):
        cantidad = min(paso, fotogramas - inicio)
        muestras = fuente.leer(inicio * MUESTRAS_POR_FOTOGRAMA, cantidad * MUESTRAS_POR_FOTOGRAMA)
        bloques = np.abs(muestras).reshape(2, cantidad, MUESTRAS_POR_FOTOGRAMA).max(axis=2)
        picos.extend([[round(float(a), 3), round(float(b), 3)] for a, b in bloques.T])
        contexto.progreso(inicio / fotogramas, f"Forma de onda de {ruta.name}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"fps": 24, "picos": picos}), encoding="utf-8")
    return destino
