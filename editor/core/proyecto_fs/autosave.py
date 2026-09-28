"""Autosave: instantánea del modelo en `.autosave/` (T5.11).

No renombra ni mueve archivos de medios: solo guarda el estado del modelo
cargado en memoria (proyecto, Taller y capítulos cargados). Al abrir, si la
instantánea es más reciente que `_proyecto.json`, se ofrece restaurarla; la
restauración deja el modelo como estaba y el siguiente guardado lo reconcilia
con el disco.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto
from editor.core.proyecto_fs import estructura
from editor.core.proyecto_fs.gemelo import elemento_a_datos, elemento_desde_datos, short_a_datos, short_desde_datos
from editor.core.proyecto_fs.manifiestos import (
    aplicar_datos_capitulo,
    aplicar_datos_minuto,
    aplicar_datos_renders,
    bruto_desde_datos,
    capitulo_a_datos,
    horneado_a_datos,
    horneado_desde_datos,
    minuto_a_datos,
    pieza_a_datos,
    pieza_desde_datos,
    proyecto_a_datos,
    proyecto_desde_datos,
    renders_a_datos,
)
from editor.core.proyecto_fs.serializacion import escribir_json_atomico, leer_json
from editor.core.tiempo.nomenclatura import CARPETA_AUTOSAVE, VERSION_ESQUEMA, NombreElemento, NombreShort

ARCHIVO_INSTANTANEA = "instantanea.json"


def ruta_instantanea(raiz: Path) -> Path:
    return raiz / CARPETA_AUTOSAVE / ARCHIVO_INSTANTANEA


def guardar_instantanea(proyecto: Proyecto) -> Path:
    assert proyecto.raiz is not None
    capitulos = {}
    for capitulo in proyecto.capitulos_cargados():
        capitulos[str(capitulo.numero)] = {
            "manifiesto": capitulo_a_datos(capitulo),
            "renders": renders_a_datos(capitulo),
            "minutos": [minuto_a_datos(m) for m in capitulo.minutos],
            "elementos": [
                {"archivo": e.nombre_archivo().archivo, "global": e.en_global, "gemelo": elemento_a_datos(e)}
                for e in capitulo.todos_los_elementos()
            ],
            "shorts": [
                {"receta": s.nombre_archivo().receta, "datos": short_a_datos(s)} for s in capitulo.shorts.values()
            ],
        }
    datos = {
        "version_esquema": VERSION_ESQUEMA,
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "proyecto": proyecto_a_datos(proyecto),
        "piezas": [
            {"receta": pieza_a_datos(p, []), "horneado": horneado_a_datos(p.horneado)}
            for p in proyecto.taller.piezas.values()
        ],
        "capitulos": capitulos,
    }
    ruta = ruta_instantanea(proyecto.raiz)
    escribir_json_atomico(ruta, datos)
    return ruta


def instantanea_mas_reciente(raiz: Path) -> Path | None:
    """La instantánea, si existe y es más reciente que el último guardado."""
    instantanea = ruta_instantanea(raiz)
    manifiesto = estructura.ruta_manifiesto_proyecto(raiz)
    if not instantanea.exists():
        return None
    if manifiesto.exists() and instantanea.stat().st_mtime_ns <= manifiesto.stat().st_mtime_ns:
        return None
    return instantanea


def descartar_instantanea(raiz: Path) -> None:
    ruta_instantanea(raiz).unlink(missing_ok=True)


def restaurar_instantanea(proyecto: Proyecto) -> None:
    """Reemplaza el modelo en memoria por el de la instantánea (el disco no se toca)."""
    assert proyecto.raiz is not None
    datos = leer_json(ruta_instantanea(proyecto.raiz))
    base = proyecto_desde_datos(datos["proyecto"])
    proyecto.nombre = base.nombre
    proyecto.idiomas = base.idiomas
    proyecto.estandar = base.estandar
    proyecto.indice_capitulos = dict(base.indice_capitulos)
    for identificador in base.ids_usados:
        proyecto.ids.registrar(identificador)

    archivos_brutos = {b.id: b.archivo for b in proyecto.taller.brutos.values()}
    proyecto.taller.brutos = {}
    for datos_bruto in datos["proyecto"].get("brutos", []):
        bruto = bruto_desde_datos(datos_bruto)
        bruto.archivo = archivos_brutos.get(bruto.id)
        proyecto.taller.brutos[bruto.id] = bruto

    archivos_horneados = {
        p.id: p.horneado.archivo for p in proyecto.taller.piezas.values() if p.horneado is not None
    }
    proyecto.taller.piezas = {}
    for datos_pieza in datos.get("piezas", []):
        pieza, _ = pieza_desde_datos(datos_pieza["receta"])
        pieza.horneado = horneado_desde_datos(datos_pieza.get("horneado"))
        if pieza.horneado is not None:
            pieza.horneado.archivo = archivos_horneados.get(pieza.id)
        proyecto.taller.piezas[pieza.id] = pieza

    for numero_texto, datos_capitulo in datos.get("capitulos", {}).items():
        numero = int(numero_texto)
        anterior = proyecto.capitulos.get(numero)
        archivos = {e.id: e.archivo for e in anterior.todos_los_elementos()} if anterior else {}
        capitulo = Capitulo(numero=numero)
        aplicar_datos_capitulo(capitulo, datos_capitulo["manifiesto"])
        for minuto, datos_minuto in zip(capitulo.minutos, datos_capitulo.get("minutos", [])):
            aplicar_datos_minuto(minuto, datos_minuto)
        for item in datos_capitulo.get("elementos", []):
            nombre = NombreElemento.desde_archivo(item["archivo"])
            elemento = elemento_desde_datos(item["gemelo"], nombre, bool(item.get("global", False)))
            elemento.archivo = archivos.get(elemento.id)
            capitulo.contenedor_de(elemento).elementos[elemento.id] = elemento
        for item in datos_capitulo.get("shorts", []):
            nombre, _ = NombreShort.desde_archivo(item["receta"])
            short = short_desde_datos(item["datos"], nombre)
            capitulo.shorts[short.id] = short
        aplicar_datos_renders(capitulo, datos_capitulo.get("renders", {}))
        proyecto.capitulos[numero] = capitulo

    proyecto.registrar_ids_cargados()
    proyecto.reconstruir_referencias()
