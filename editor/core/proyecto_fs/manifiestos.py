"""Archivos de control: `_proyecto.json`, `_capitulo.json`, `_minuto.json`, `_pieza.json`.

Todos llevan `version_esquema` para poder migrar proyectos en el futuro.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from editor.core.estandar import Estandar
from editor.core.modelo.bruto import Bruto, TipoMedio
from editor.core.modelo.capitulo import Capitulo, RegistroRender
from editor.core.modelo.minuto import Minuto, RegistroRenderMinuto
from editor.core.modelo.pieza import AudioConformado, Horneado, MetodoConversionFps, Pieza, TramoFuente
from editor.core.modelo.proyecto import Proyecto
from editor.core.proyecto_fs.serializacion import (
    Datos,
    efecto_a_datos,
    efecto_desde_datos,
    estado_capa_a_datos,
    estado_capa_desde_datos,
    fraccion_a_texto,
    fraccion_desde_texto,
    marcador_a_datos,
    marcador_desde_datos,
    transform_a_datos,
    transform_desde_datos,
)
from editor.core.tiempo.nomenclatura import VERSION_ESQUEMA, NombreRender


class EsquemaIncompatible(ValueError):
    pass


def verificar_esquema(datos: Datos, archivo: str) -> None:
    version = int(datos.get("version_esquema", 1))
    if version > VERSION_ESQUEMA:
        raise EsquemaIncompatible(
            f"{archivo} usa el esquema {version}; este programa entiende hasta el {VERSION_ESQUEMA}."
        )


# --- Proyecto ----------------------------------------------------------------------

def bruto_a_datos(bruto: Bruto) -> Datos:
    return {
        "id": bruto.id,
        "numero": bruto.numero,
        "nombre": bruto.nombre,
        "tipo": bruto.tipo.value,
        "extension": bruto.extension,
        "ancho": bruto.ancho,
        "alto": bruto.alto,
        "fotogramas_nativos": bruto.fotogramas_nativos,
        "fps_detectado": fraccion_a_texto(bruto.fps_detectado),
        "fps_medido": fraccion_a_texto(bruto.fps_medido),
        "fps_interpretado": fraccion_a_texto(bruto.fps_interpretado),
        "vfr": bruto.vfr,
        "tiene_alfa": bruto.tiene_alfa,
        "tiene_audio": bruto.tiene_audio,
        "audio_frecuencia": bruto.audio_frecuencia,
        "origen": bruto.origen,
    }


def bruto_desde_datos(datos: Datos) -> Bruto:
    return Bruto(
        id=datos["id"],
        numero=int(datos["numero"]),
        nombre=datos["nombre"],
        tipo=TipoMedio(datos["tipo"]),
        extension=datos["extension"],
        ancho=int(datos.get("ancho", 0)),
        alto=int(datos.get("alto", 0)),
        fotogramas_nativos=int(datos.get("fotogramas_nativos", 0)),
        fps_detectado=fraccion_desde_texto(datos.get("fps_detectado")),
        fps_medido=fraccion_desde_texto(datos.get("fps_medido")),
        fps_interpretado=fraccion_desde_texto(datos.get("fps_interpretado")),
        vfr=bool(datos.get("vfr", False)),
        tiene_alfa=bool(datos.get("tiene_alfa", False)),
        tiene_audio=bool(datos.get("tiene_audio", False)),
        audio_frecuencia=int(datos.get("audio_frecuencia", 0)),
        origen=datos.get("origen", ""),
    )


def proyecto_a_datos(proyecto: Proyecto) -> Datos:
    return {
        "version_esquema": VERSION_ESQUEMA,
        "nombre": proyecto.nombre,
        "idiomas": list(proyecto.idiomas),
        "estandar": proyecto.estandar.a_dict(),
        "capitulos": {str(n): proyecto.indice_capitulos[n] for n in sorted(proyecto.indice_capitulos)},
        "ids_usados": sorted(proyecto.ids.usados),
        "brutos": [bruto_a_datos(b) for b in sorted(proyecto.taller.brutos.values(), key=lambda b: b.numero)],
    }


@dataclass
class DatosProyecto:
    """Lo que `_proyecto.json` aporta al abrir; el escáner arma el Proyecto con esto."""

    nombre: str
    idiomas: list[str]
    estandar: Estandar
    indice_capitulos: dict[int, str]
    ids_usados: set[str]
    brutos: list[Bruto] = field(default_factory=list)


def proyecto_desde_datos(datos: Datos) -> DatosProyecto:
    verificar_esquema(datos, "_proyecto.json")
    return DatosProyecto(
        nombre=datos.get("nombre", ""),
        idiomas=list(datos.get("idiomas", ["es"])) or ["es"],
        estandar=Estandar.desde_dict(datos.get("estandar", {})),
        indice_capitulos={int(n): str(t) for n, t in datos.get("capitulos", {}).items()},
        ids_usados=set(datos.get("ids_usados", [])),
        brutos=[bruto_desde_datos(b) for b in datos.get("brutos", [])],
    )


# --- Capítulo y minuto ---------------------------------------------------------------

def capitulo_a_datos(capitulo: Capitulo) -> Datos:
    return {
        "version_esquema": VERSION_ESQUEMA,
        "numero": capitulo.numero,
        "titulo": capitulo.titulo,
        "capas": {clave: estado_capa_a_datos(e) for clave, e in sorted(capitulo.capas.items())},
        "marcadores": [marcador_a_datos(m) for m in sorted(capitulo.marcadores, key=lambda m: m.f)],
    }


def aplicar_datos_capitulo(capitulo: Capitulo, datos: Datos) -> None:
    verificar_esquema(datos, "_capitulo.json")
    capitulo.titulo = datos.get("titulo", capitulo.titulo)
    capitulo.capas = {clave: estado_capa_desde_datos(e) for clave, e in datos.get("capas", {}).items()}
    capitulo.marcadores = [marcador_desde_datos(m) for m in datos.get("marcadores", [])]


def minuto_a_datos(minuto: Minuto) -> Datos:
    return {
        "numero": minuto.numero,
        "listo": minuto.listo,
        "notas": minuto.notas,
    }


def aplicar_datos_minuto(minuto: Minuto, datos: Datos) -> None:
    minuto.listo = bool(datos.get("listo", False))
    minuto.notas = datos.get("notas", "")


# --- Estado automático ------------------------------------------------------------------
#
# Lo escriben los servicios en el momento (render, horneado), en archivos propios,
# para no mezclarlo con lo que el usuario edita y guarda cuando quiere.

def renders_a_datos(capitulo: Capitulo) -> Datos:
    """`capNNNN/render/_renders.json`: entregables, último render de cada minuto y de cada Short."""
    return {
        "version_esquema": VERSION_ESQUEMA,
        "entregables": [{"archivo": r.nombre.archivo, "huella": r.huella} for r in capitulo.renders],
        "minutos": {
            f"{m.numero:02d}": {"version": m.ultimo_render.version, "huella": m.ultimo_render.huella}
            for m in capitulo.minutos if m.ultimo_render is not None
        },
        "shorts": {
            s.id: {"version": s.ultimo_render.version, "huella": s.ultimo_render.huella}
            for s in capitulo.shorts.values() if s.ultimo_render is not None
        },
    }


def aplicar_datos_renders(capitulo: Capitulo, datos: Datos) -> None:
    from editor.core.modelo.short import RegistroRenderShort

    capitulo.renders = [
        RegistroRender(NombreRender.desde_archivo(r["archivo"]), r["huella"]) for r in datos.get("entregables", [])
    ]
    for numero, render in datos.get("minutos", {}).items():
        capitulo.minuto(int(numero)).ultimo_render = RegistroRenderMinuto(int(render["version"]), str(render["huella"]))
    for identificador, render in datos.get("shorts", {}).items():
        short = capitulo.shorts.get(identificador)
        if short is not None:
            short.ultimo_render = RegistroRenderShort(int(render["version"]), str(render["huella"]))


def horneado_a_datos(horneado: Horneado | None) -> Datos:
    """`taller/pieNNNN…/_horneado.json`: resultado del último horneado."""
    if horneado is None:
        return {"version_esquema": VERSION_ESQUEMA, "horneado": None}
    return {
        "version_esquema": VERSION_ESQUEMA,
        "horneado": {
            "version": horneado.version,
            "extension": horneado.extension,
            "ancho": horneado.ancho,
            "alto": horneado.alto,
            "fotogramas": horneado.fotogramas,
            "asas_inicio": horneado.asas_inicio,
            "asas_fin": horneado.asas_fin,
            "tiene_alfa": horneado.tiene_alfa,
            "tiene_audio": horneado.tiene_audio,
        },
    }


def horneado_desde_datos(datos: Datos | None) -> Horneado | None:
    horneado = (datos or {}).get("horneado")
    if not horneado:
        return None
    return Horneado(
        version=int(horneado["version"]),
        extension=horneado["extension"],
        ancho=int(horneado.get("ancho", 0)),
        alto=int(horneado.get("alto", 0)),
        fotogramas=int(horneado.get("fotogramas", 0)),
        asas_inicio=int(horneado.get("asas_inicio", 0)),
        asas_fin=int(horneado.get("asas_fin", 0)),
        tiene_alfa=bool(horneado.get("tiene_alfa", False)),
        tiene_audio=bool(horneado.get("tiene_audio", False)),
    )


# --- Pieza -------------------------------------------------------------------------

@dataclass(frozen=True)
class Copia:
    """Dónde hay una copia materializada de una Pieza (para no cargar capítulos al volver a hornear)."""

    capitulo: int
    minuto: int | None
    id_elemento: str


def pieza_a_datos(pieza: Pieza, copias: list[Copia]) -> Datos:
    """Receta de la Pieza (lo que edita el usuario). El horneado va en `_horneado.json`."""
    return {
        "version_esquema": VERSION_ESQUEMA,
        "id": pieza.id,
        "numero": pieza.numero,
        "nombre": pieza.nombre,
        "tramos": [{"id_bruto": t.id_bruto, "entrada": t.entrada, "salida": t.salida} for t in pieza.tramos],
        "metodo_fps": pieza.metodo_fps.value,
        "audio_conformado": pieza.audio_conformado.value,
        "espacio": transform_a_datos(pieza.espacio),
        "efectos": [efecto_a_datos(e) for e in pieza.efectos],
        "receta_modificada": pieza.receta_modificada,
        "copias": [
            {"capitulo": c.capitulo, "minuto": c.minuto, "id": c.id_elemento}
            for c in sorted(copias, key=lambda c: (c.capitulo, -1 if c.minuto is None else c.minuto, c.id_elemento))
        ],
    }


def pieza_desde_datos(datos: Datos) -> tuple[Pieza, list[Copia]]:
    verificar_esquema(datos, "_pieza.json")
    pieza = Pieza(
        id=datos["id"],
        numero=int(datos["numero"]),
        nombre=datos["nombre"],
        tramos=[TramoFuente(t["id_bruto"], int(t["entrada"]), int(t["salida"])) for t in datos.get("tramos", [])],
        metodo_fps=MetodoConversionFps(datos.get("metodo_fps", MetodoConversionFps.TIEMPO.value)),
        audio_conformado=AudioConformado(datos.get("audio_conformado", AudioConformado.ESTIRAR_CON_TONO.value)),
        espacio=transform_desde_datos(datos.get("espacio")),
        efectos=[efecto_desde_datos(e) for e in datos.get("efectos", [])],
        receta_modificada=bool(datos.get("receta_modificada", True)),
    )
    copias = [
        Copia(int(c["capitulo"]), None if c.get("minuto") is None else int(c["minuto"]), c["id"])
        for c in datos.get("copias", [])
    ]
    return pieza, copias
