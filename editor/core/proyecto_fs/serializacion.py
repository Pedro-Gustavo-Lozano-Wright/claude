"""Serialización canónica del modelo a JSON.

Una sola forma de convertir cada tipo a datos JSON y de vuelta. Es canónica
(claves ordenadas, sin espacios variables) para que el mismo modelo produzca
siempre el mismo texto: así se detecta qué gemelos cambiaron y se calculan las
huellas de render sin falsos positivos.

Solo convierte datos; leer y escribir archivos es cosa de `gemelo`,
`manifiestos` y `diario`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any

from editor.core.espacio.transform import Recorte, Transform
from editor.core.modelo.efecto import Efecto
from editor.core.modelo.keyframe import Animacion, Keyframe, PistaKeyframes
from editor.core.modelo.marcador import EstadoCapa, Marcador
from editor.core.modelo.texto import ContenidoTexto, EstiloTexto, Sombra
from editor.core.modelo.transicion import Transicion

Datos = dict[str, Any]


# --- JSON canónico --------------------------------------------------------------

def json_canonico(datos: Any) -> str:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def json_legible(datos: Any) -> str:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def huella(datos: Any) -> str:
    """Resumen estable de unos datos (SHA-256 del JSON canónico, 16 hexadecimales)."""
    return hashlib.sha256(json_canonico(datos).encode("utf-8")).hexdigest()[:16]


def huella_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def leer_json(ruta: Path) -> Any:
    with ruta.open(encoding="utf-8") as archivo:
        return json.load(archivo)


def _umask_actual() -> int:
    actual = os.umask(0)
    os.umask(actual)
    return actual


_UMASK = _umask_actual()


def escribir_texto_atomico(ruta: Path, texto: str) -> None:
    """Escribe en un temporal del mismo directorio y lo reemplaza de una vez."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(prefix=".tmp_", dir=ruta.parent)
    try:
        # mkstemp crea con 0600; los archivos del proyecto llevan los permisos normales (umask).
        os.fchmod(descriptor, 0o666 & ~_UMASK)
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            archivo.write(texto)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def escribir_json_atomico(ruta: Path, datos: Any) -> None:
    escribir_texto_atomico(ruta, json_legible(datos))


# --- Tipos simples ---------------------------------------------------------------

def fraccion_a_texto(valor: Fraction | None) -> str | None:
    if valor is None:
        return None
    return str(valor.numerator) if valor.denominator == 1 else f"{valor.numerator}/{valor.denominator}"


def fraccion_desde_texto(texto: str | None) -> Fraction | None:
    if texto in (None, ""):
        return None
    return Fraction(str(texto))


def _numero(valor: float) -> float | int:
    """Enteros sin decimales en el JSON (200 en vez de 200.0)."""
    return int(valor) if float(valor).is_integer() else float(valor)


# --- Espacio ----------------------------------------------------------------------

def transform_a_datos(transform: Transform) -> Datos:
    return {
        "x": _numero(transform.x),
        "y": _numero(transform.y),
        "ancla_x": _numero(transform.ancla_x),
        "ancla_y": _numero(transform.ancla_y),
        "escala_x": _numero(transform.escala_x),
        "escala_y": _numero(transform.escala_y),
        "rotacion": _numero(transform.rotacion),
        "recorte": [_numero(v) for v in transform.recorte.como_lista()],
        "opacidad": _numero(transform.opacidad),
        "mezcla": transform.mezcla,
    }


def transform_desde_datos(datos: Datos | None) -> Transform:
    if not datos:
        return Transform()
    return Transform(
        x=float(datos.get("x", 0.0)),
        y=float(datos.get("y", 0.0)),
        ancla_x=float(datos.get("ancla_x", 0.0)),
        ancla_y=float(datos.get("ancla_y", 0.0)),
        escala_x=float(datos.get("escala_x", 1.0)),
        escala_y=float(datos.get("escala_y", 1.0)),
        rotacion=float(datos.get("rotacion", 0.0)),
        recorte=Recorte.desde_lista(datos.get("recorte", [0, 0, 0, 0])),
        opacidad=float(datos.get("opacidad", 1.0)),
        mezcla=datos.get("mezcla", "normal"),
    )


# --- Animación --------------------------------------------------------------------

def keyframe_a_datos(keyframe: Keyframe) -> Datos:
    datos: Datos = {"f": keyframe.f, "valor": _numero(keyframe.valor), "curva": keyframe.curva}
    if keyframe.controles is not None:
        datos["controles"] = [_numero(v) for v in keyframe.controles]
    return datos


def keyframe_desde_datos(datos: Datos) -> Keyframe:
    controles = datos.get("controles")
    return Keyframe(
        f=int(datos["f"]),
        valor=float(datos["valor"]),
        curva=datos.get("curva", "lineal"),
        controles=tuple(float(v) for v in controles) if controles else None,  # type: ignore[arg-type]
    )


def animacion_a_datos(animacion: Animacion) -> Datos:
    return {
        propiedad: [keyframe_a_datos(k) for k in pista]
        for propiedad, pista in sorted(animacion.pistas.items())
        if not pista.vacia
    }


def animacion_desde_datos(datos: Datos | None) -> Animacion:
    if not datos:
        return Animacion()
    return Animacion({
        propiedad: PistaKeyframes([keyframe_desde_datos(k) for k in keyframes])
        for propiedad, keyframes in datos.items()
    })


# --- Efectos, transiciones y texto -------------------------------------------------

def efecto_a_datos(efecto: Efecto) -> Datos:
    return {
        "tipo": efecto.tipo,
        "parametros": {k: _numero(v) for k, v in sorted(efecto.parametros.items())},
        "opciones": dict(sorted(efecto.opciones.items())),
        "activo": efecto.activo,
        "keyframes": animacion_a_datos(efecto.animacion),
    }


def efecto_desde_datos(datos: Datos) -> Efecto:
    return Efecto(
        tipo=datos["tipo"],
        parametros={k: float(v) for k, v in datos.get("parametros", {}).items()},
        opciones={k: str(v) for k, v in datos.get("opciones", {}).items()},
        activo=bool(datos.get("activo", True)),
        animacion=animacion_desde_datos(datos.get("keyframes")),
    )


def transicion_a_datos(transicion: Transicion | None) -> Datos | None:
    if transicion is None:
        return None
    return {"tipo": transicion.tipo, "duracion": transicion.duracion, "direccion": transicion.direccion}


def transicion_desde_datos(datos: Datos | None) -> Transicion | None:
    if not datos:
        return None
    return Transicion(
        tipo=datos.get("tipo", "fundido"),
        duracion=int(datos.get("duracion", 12)),
        direccion=datos.get("direccion", "izquierda"),
    )


def texto_a_datos(contenido: ContenidoTexto | None) -> Datos | None:
    if contenido is None:
        return None
    estilo = contenido.estilo
    return {
        "texto": contenido.texto,
        "estilo": {
            "fuente": estilo.fuente,
            "tamano": _numero(estilo.tamano),
            "color": estilo.color,
            "contorno_color": estilo.contorno_color,
            "contorno_ancho": _numero(estilo.contorno_ancho),
            "sombra": None if estilo.sombra is None else {
                "color": estilo.sombra.color,
                "desplazamiento_x": _numero(estilo.sombra.desplazamiento_x),
                "desplazamiento_y": _numero(estilo.sombra.desplazamiento_y),
                "desenfoque": _numero(estilo.sombra.desenfoque),
            },
            "alineacion": estilo.alineacion,
            "interlineado": _numero(estilo.interlineado),
            "ancho_maximo": _numero(estilo.ancho_maximo),
        },
        "animacion_entrada": contenido.animacion_entrada,
        "animacion_salida": contenido.animacion_salida,
        "duracion_animacion": contenido.duracion_animacion,
    }


def texto_desde_datos(datos: Datos | None) -> ContenidoTexto | None:
    if datos is None:
        return None
    estilo_datos = datos.get("estilo", {})
    sombra_datos = estilo_datos.get("sombra")
    estilo = EstiloTexto(
        fuente=estilo_datos.get("fuente", ""),
        tamano=float(estilo_datos.get("tamano", 48.0)),
        color=estilo_datos.get("color", "#ffffffff"),
        contorno_color=estilo_datos.get("contorno_color", "#000000ff"),
        contorno_ancho=float(estilo_datos.get("contorno_ancho", 0.0)),
        sombra=None if sombra_datos is None else Sombra(
            color=sombra_datos.get("color", "#000000aa"),
            desplazamiento_x=float(sombra_datos.get("desplazamiento_x", 2.0)),
            desplazamiento_y=float(sombra_datos.get("desplazamiento_y", 2.0)),
            desenfoque=float(sombra_datos.get("desenfoque", 4.0)),
        ),
        alineacion=estilo_datos.get("alineacion", "centro"),
        interlineado=float(estilo_datos.get("interlineado", 1.2)),
        ancho_maximo=float(estilo_datos.get("ancho_maximo", 0.0)),
    )
    return ContenidoTexto(
        texto=datos.get("texto", ""),
        estilo=estilo,
        animacion_entrada=datos.get("animacion_entrada", "ninguna"),
        animacion_salida=datos.get("animacion_salida", "ninguna"),
        duracion_animacion=int(datos.get("duracion_animacion", 12)),
    )


# --- Capas y marcadores -------------------------------------------------------------

def estado_capa_a_datos(estado: EstadoCapa) -> Datos:
    return {
        "visible": estado.visible,
        "silenciada": estado.silenciada,
        "bloqueada": estado.bloqueada,
        "solo": estado.solo,
        "idioma": estado.idioma,
    }


def estado_capa_desde_datos(datos: Datos) -> EstadoCapa:
    return EstadoCapa(
        visible=bool(datos.get("visible", True)),
        silenciada=bool(datos.get("silenciada", False)),
        bloqueada=bool(datos.get("bloqueada", False)),
        solo=bool(datos.get("solo", False)),
        idioma=str(datos.get("idioma", "")),
    )


def marcador_a_datos(marcador: Marcador) -> Datos:
    return {"f": marcador.f, "nombre": marcador.nombre, "nota": marcador.nota, "color": marcador.color}


def marcador_desde_datos(datos: Datos) -> Marcador:
    return Marcador(
        f=int(datos["f"]),
        nombre=datos.get("nombre", ""),
        nota=datos.get("nota", ""),
        color=datos.get("color", "amarillo"),
    )
