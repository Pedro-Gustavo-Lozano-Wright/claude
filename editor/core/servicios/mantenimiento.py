"""Mantenimiento del proyecto (E18): espacio en disco, tamaños, caché, papelera y Brutos sin uso.

- `comprobar_espacio` se llama antes de hornear y renderizar (importar ya lo hace).
- La caché se regenera sola; la papelera guarda lo que un guardado reemplazó y
  permite deshacer después de guardar: vaciarla obliga a olvidar el historial.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from editor.core.modelo.proyecto import Proyecto
from editor.core.proyecto_fs import consultas
from editor.core.servicios.importacion import EspacioInsuficiente
from editor.core.tiempo.nomenclatura import CARPETA_CACHE

MARGEN_BYTES = 500 * 1024 * 1024          # siempre dejar libre al menos esto
BYTES_POR_PIXEL_H264 = 0.08               # estimación prudente por fotograma codificado
BYTES_POR_PIXEL_PRORES = 1.2              # ProRes 4444 con alfa
CARPETA_PAPELERA = ".papelera"


def comprobar_espacio(raiz: Path, necesarios: int, que: str) -> None:
    libre = shutil.disk_usage(raiz).free
    if libre < necesarios + MARGEN_BYTES:
        falta = (necesarios + MARGEN_BYTES - libre) / 1e9
        raise EspacioInsuficiente(f"Faltan {falta:.1f} GB de disco para {que}.")


def estimar_video(fotogramas: int, ancho: int, alto: int, con_alfa: bool = False) -> int:
    por_pixel = BYTES_POR_PIXEL_PRORES if con_alfa else BYTES_POR_PIXEL_H264
    return int(fotogramas * ancho * alto * por_pixel)


def tamano(ruta: Path) -> int:
    if not ruta.exists():
        return 0
    if ruta.is_file():
        return ruta.stat().st_size
    return sum(p.stat().st_size for p in ruta.rglob("*") if p.is_file())


def tamanos(raiz: Path) -> dict[str, int]:
    """Bytes por zona del proyecto, para el diálogo de mantenimiento."""
    zonas = {
        "Brutos": raiz / "brutos",
        "Taller (horneados)": raiz / "taller",
        "Caché de vista previa": raiz / CARPETA_CACHE,
        "Papelera": raiz / CARPETA_PAPELERA,
    }
    resultado = {nombre: tamano(ruta) for nombre, ruta in zonas.items()}
    resultado["Capítulos"] = sum(tamano(c) for c in raiz.glob("cap[0-9][0-9][0-9][0-9]*") if c.is_dir())
    resultado["Libre en el disco"] = shutil.disk_usage(raiz).free
    return resultado


def vaciar_cache(raiz: Path) -> int:
    """Borra `.cache/` (banco, miniaturas, ondas, pre-renders, audio). Devuelve los bytes liberados."""
    return _vaciar(raiz / CARPETA_CACHE)


def vaciar_papelera(raiz: Path) -> int:
    return _vaciar(raiz / CARPETA_PAPELERA)


def _vaciar(carpeta: Path) -> int:
    liberados = tamano(carpeta)
    if carpeta.exists():
        shutil.rmtree(carpeta)
    return liberados


def brutos_sin_uso(proyecto: Proyecto) -> list[str]:
    """IDs de Brutos que no son fuente de ninguna Pieza ni de ningún Elemento (de ningún capítulo).

    El capítulo cargado se mira en el índice; los demás, en sus gemelos en disco.
    """
    assert proyecto.raiz is not None
    en_disco = consultas.fuentes_en_disco(proyecto.raiz, {c.numero for c in proyecto.capitulos_cargados()})
    resultado = []
    for identificador in proyecto.taller.brutos:
        piezas, elementos = proyecto.referencias.dependientes_de_bruto(identificador)
        if not piezas and not elementos and identificador not in en_disco:
            resultado.append(identificador)
    return sorted(resultado, key=lambda i: proyecto.taller.brutos[i].numero)
