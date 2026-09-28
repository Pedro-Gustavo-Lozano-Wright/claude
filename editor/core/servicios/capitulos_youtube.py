"""Capítulos de YouTube desde los marcadores (E21).

YouTube los lee de la descripción del video: una línea `M:SS Título` por
capítulo, el primero en 0:00, al menos 3 y cada uno de 10 s o más. Si falta
un marcador al comienzo se agrega "Inicio".
"""

from __future__ import annotations

from editor.core.estandar import FPS
from editor.core.modelo.capitulo import Capitulo

MINIMO_CAPITULOS = 3
DURACION_MINIMA = 10 * FPS


def _tiempo(f: int) -> str:
    segundos = f // FPS
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def capitulos(capitulo: Capitulo, inicio: int, fin: int) -> tuple[str, list[str]]:
    """(texto para la descripción, avisos). Texto vacío si no hay marcadores en el rango."""
    marcadores = capitulo.marcadores_en_rango(inicio, fin)
    if not marcadores:
        return "", []
    puntos: list[tuple[int, str]] = []
    for i, marcador in enumerate(marcadores, 1):
        puntos.append((marcador.f - inicio, marcador.nombre.strip() or f"Parte {i}"))
    if puntos[0][0] >= FPS:
        puntos.insert(0, (0, "Inicio"))
    else:
        puntos[0] = (0, puntos[0][1])
    avisos = []
    if len(puntos) < MINIMO_CAPITULOS:
        avisos.append(f"YouTube necesita al menos {MINIMO_CAPITULOS} capítulos (hay {len(puntos)}).")
    cortos = [titulo for (f, titulo), (siguiente, _) in zip(puntos, puntos[1:] + [(fin - inicio, "")])
              if siguiente - f < DURACION_MINIMA]
    if cortos:
        avisos.append("Duran menos de 10 s: " + ", ".join(cortos) + ".")
    return "\n".join(f"{_tiempo(f)} {titulo}" for f, titulo in puntos), avisos
