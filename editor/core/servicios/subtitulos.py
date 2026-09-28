"""Subtítulos `.srt`: leer para crear Elementos de texto y escribir desde una capa T.

Los tiempos se redondean al fotograma de 24 fps. Leer tolera BOM, CRLF,
etiquetas <i>/<b> (se quitan) y numeraciones faltantes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from editor.core.estandar import FPS
from editor.core.modelo.capitulo import Capitulo

_TIEMPO = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")
_ETIQUETA = re.compile(r"</?[a-zA-Z][^>]*>")


@dataclass(frozen=True)
class Subtitulo:
    inicio: int      # fotograma
    fin: int         # fotograma (excluido)
    texto: str


def _a_fotograma(h: str, m: str, s: str, ms: str) -> int:
    segundos = int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000
    return round(segundos * FPS)


def leer_srt(ruta: Path) -> list[Subtitulo]:
    texto = ruta.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    resultado: list[Subtitulo] = []
    for bloque in re.split(r"\n\s*\n", texto.strip()):
        lineas = [l for l in bloque.split("\n") if l.strip()]
        for i, linea in enumerate(lineas):
            coincidencia = _TIEMPO.search(linea)
            if coincidencia:
                g = coincidencia.groups()
                inicio, fin = _a_fotograma(*g[:4]), _a_fotograma(*g[4:])
                contenido = _ETIQUETA.sub("", "\n".join(lineas[i + 1:])).strip()
                if contenido and fin > inicio:
                    resultado.append(Subtitulo(inicio, fin, contenido))
                break
    resultado.sort(key=lambda s: s.inicio)
    # Un subtítulo termina donde empieza el siguiente si se pisaban (la capa no admite solapes).
    ajustados: list[Subtitulo] = []
    for actual, siguiente in zip(resultado, resultado[1:] + [None]):
        fin = min(actual.fin, siguiente.inicio) if siguiente is not None else actual.fin
        if fin > actual.inicio:
            ajustados.append(Subtitulo(actual.inicio, fin, actual.texto))
    return ajustados


def _formato(f: int) -> str:
    total_ms = round(f * 1000 / FPS)
    h, resto = divmod(total_ms, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, ms = divmod(resto, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _bloques(textos, desplazamiento: int = 0, limite: int | None = None) -> list[str]:
    bloques = []
    for e in sorted(textos, key=lambda e: e.inicio):
        inicio = max(0, e.inicio - desplazamiento)
        fin = e.fin - desplazamiento if limite is None else min(e.fin - desplazamiento, limite)
        if fin > inicio:
            bloques.append(f"{len(bloques) + 1}\n{_formato(inicio)} --> {_formato(fin)}\n{e.texto.texto}\n")
    return bloques


def escribir_srt(capitulo: Capitulo, codigo_capa: str, ruta: Path, en_global: bool = False) -> int:
    """Escribe los textos de una capa T como `.srt`. Devuelve cuántos subtítulos escribió."""
    fuente = capitulo.global_ if en_global else capitulo.elementos_de_minutos()
    bloques = _bloques(e for e in fuente if e.es_texto and e.capa.codigo == codigo_capa and e.texto is not None)
    ruta.write_text("\n".join(bloques), encoding="utf-8")
    return len(bloques)


def srt_de_idioma(capitulo: Capitulo, idioma: str, inicio: int, fin: int) -> str | None:
    """Subtítulos de un idioma (textos de las capas T con ese idioma) en el rango, con tiempos
    desde `inicio`. None si no hay ninguno. Es lo que acompaña al render."""
    textos = [
        e for e in list(capitulo.elementos_de_minutos()) + list(capitulo.global_)
        if e.es_texto and e.texto is not None and capitulo.estado_capa(e).idioma == idioma
        and e.inicio < fin and inicio < e.fin
    ]
    bloques = _bloques(textos, inicio, fin - inicio)
    return "\n".join(bloques) if bloques else None
