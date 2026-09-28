"""Huellas y estado de render de cada minuto (T10.1, PROJECT.md 13.2).

La huella de video de un minuto resume todo lo que cambia su imagen: sus
Elementos, los desbordes que entran desde minutos anteriores, lo de Global que
lo cruza, el estado de las capas, la firma de cada archivo fuente y el
estándar. La huella de audio se calcula por idioma (13.6): cambiar el diálogo
en inglés no invalida la versión en español.
"""

from __future__ import annotations

from typing import Callable

from editor.core.estandar import Estandar
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.minuto import EstadoRender
from editor.core.proyecto_fs.estado_disco import Firma
from editor.core.proyecto_fs.gemelo import elemento_a_datos
from editor.core.proyecto_fs.serializacion import estado_capa_a_datos, huella
from editor.core.tiempo import granularidad

Resolutor = Callable[[Elemento], "object"]


def _firma(resolver: Resolutor, elemento: Elemento) -> list[int] | None:
    if elemento.es_texto:
        return None
    ruta = resolver(elemento)
    firma = Firma.de(ruta) if ruta is not None else None  # type: ignore[arg-type]
    return None if firma is None else [firma.tamano, firma.modificado_ns]


def _elementos(capitulo: Capitulo, elementos: list[Elemento], resolver: Resolutor) -> list[dict]:
    return sorted(
        (
            {
                "id": e.id,
                "global": e.en_global,
                "inicio": e.inicio,
                "capa": e.capa.codigo,
                "datos": elemento_a_datos(e),
                "firma": _firma(resolver, e),
                "capa_estado": estado_capa_a_datos(capitulo.estado_capa(e)),
            }
            for e in elementos
        ),
        key=lambda d: d["id"],
    )


def huella_video_minuto(capitulo: Capitulo, numero: int, estandar: Estandar, resolver: Resolutor) -> str:
    # Los subtítulos (textos de capas T con idioma) no se dibujan en el video común: van en `.srt`.
    visuales = [e for e in capitulo.que_afecta_al_minuto(numero) if e.es_visual and capitulo.se_ve_en_idioma(e, None)]
    return huella({
        "tipo": "video",
        "minuto": numero,
        "estandar": estandar.a_dict(),
        "elementos": _elementos(capitulo, visuales, resolver),
    })


def huella_audio(capitulo: Capitulo, inicio: int, fin: int, idioma: str | None, resolver: Resolutor) -> str:
    sonoros = [
        e for e in list(capitulo.elementos_de_minutos()) + list(capitulo.global_)
        if e.suena and e.inicio < fin and inicio < e.fin and capitulo.se_oye(e, idioma)
    ]
    return huella({
        "tipo": "audio",
        "rango": [inicio, fin],
        "idioma": idioma,
        "elementos": _elementos(capitulo, sonoros, resolver),
    })


def huella_minuto(capitulo: Capitulo, numero: int, estandar: Estandar, resolver: Resolutor, idioma: str | None) -> str:
    """Video + audio del minuto: la usa el pre-render de vista previa (nivel 3)."""
    inicio, fin = granularidad.rango_minuto(numero)
    return huella([
        huella_video_minuto(capitulo, numero, estandar, resolver),
        huella_audio(capitulo, inicio, fin, idioma, resolver),
    ])


def estado_render(capitulo: Capitulo, numero: int, estandar: Estandar, resolver: Resolutor) -> EstadoRender:
    return capitulo.minuto(numero).estado_render(huella_video_minuto(capitulo, numero, estandar, resolver))
