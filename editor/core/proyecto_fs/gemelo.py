"""Gemelo .json de cada Elemento y receta .json de cada Short.

Regla de lectura: **el nombre del archivo manda** en inicio, duración, capa,
nombre descriptivo, ID y extensión (es la historia, y el usuario puede haberlo
renombrado a mano). El gemelo aporta todo lo demás: espacio, keyframes,
efectos, transición, audio, texto. Si falta el gemelo, el Elemento se rescata
solo con el nombre y valores por defecto.
"""

from __future__ import annotations

from pathlib import Path

from editor.core.modelo.capa import Capa
from editor.core.modelo.elemento import (
    AudioElemento,
    Elemento,
    EstadoElemento,
    ReferenciaFuente,
    TiempoElemento,
    TipoFuente,
)
from editor.core.modelo.short import Short, VentanaVertical
from editor.core.proyecto_fs.serializacion import (
    Datos,
    animacion_a_datos,
    animacion_desde_datos,
    efecto_a_datos,
    efecto_desde_datos,
    escribir_json_atomico,
    json_legible,
    leer_json,
    texto_a_datos,
    texto_desde_datos,
    transform_a_datos,
    transform_desde_datos,
    transicion_a_datos,
    transicion_desde_datos,
)
from editor.core.tiempo.granularidad import Duracion, Instante
from editor.core.tiempo.nomenclatura import NombreElemento, NombreShort


# --- Elementos ---------------------------------------------------------------------

def elemento_a_datos(elemento: Elemento) -> Datos:
    tiempo = elemento.tiempo
    datos: Datos = {
        "id": elemento.id,
        "fuente": {
            "tipo": elemento.fuente.tipo.value,
            "ref": elemento.fuente.ref,
            "version": elemento.fuente.version,
        },
        "tiempo": {
            "inicio": Instante(tiempo.inicio).texto(),
            "duracion": Duracion(tiempo.duracion).texto(),
            "fuente_entrada": tiempo.fuente_entrada,
            "fuente_duracion": tiempo.fuente_duracion,
            "velocidad": tiempo.velocidad,
            "congelado": tiempo.congelado,
        },
        "medio": {
            "extension": elemento.extension,
            "ancho": elemento.ancho,
            "alto": elemento.alto,
            "tiene_alfa": elemento.tiene_alfa,
            "tiene_audio": elemento.tiene_audio,
        },
        "espacio": transform_a_datos(elemento.espacio),
        "keyframes": animacion_a_datos(elemento.animacion),
        "efectos": [efecto_a_datos(e) for e in elemento.efectos],
        "transicion_entrada": transicion_a_datos(elemento.transicion_entrada),
        "audio": {
            "volumen": elemento.audio.volumen,
            "paneo": elemento.audio.paneo,
            "silenciado": elemento.audio.silenciado,
            "fundido_entrada": elemento.audio.fundido_entrada,
            "fundido_salida": elemento.audio.fundido_salida,
        },
        "estado": {"activo": elemento.estado.activo, "bloqueado": elemento.estado.bloqueado},
    }
    if elemento.texto is not None:
        datos["texto"] = texto_a_datos(elemento.texto)
    return datos


def elemento_desde_datos(datos: Datos | None, nombre: NombreElemento, en_global: bool) -> Elemento:
    """Reconstruye un Elemento. Con `datos` None (gemelo perdido) usa valores por defecto."""
    datos = datos or {}
    fuente_datos = datos.get("fuente", {})
    tiempo_datos = datos.get("tiempo", {})
    medio = datos.get("medio", {})
    audio = datos.get("audio", {})
    estado = datos.get("estado", {})
    capa = Capa.desde_codigo(nombre.capa)

    tipo_fuente = TipoFuente(fuente_datos.get("tipo", TipoFuente.PIEZA.value))
    fuente = ReferenciaFuente(tipo_fuente, str(fuente_datos.get("ref", "")), int(fuente_datos.get("version", 0)))
    entrada_por_defecto = 0 if tipo_fuente is not TipoFuente.PIEZA else None

    tiempo = TiempoElemento(
        inicio=nombre.inicio.fotograma,
        duracion=nombre.duracion.fotogramas,
        velocidad=float(tiempo_datos.get("velocidad", 1.0)),
        fuente_duracion=int(tiempo_datos.get("fuente_duracion", 0)),
        congelado=bool(tiempo_datos.get("congelado", False)),
    )
    if "fuente_entrada" in tiempo_datos:
        tiempo.fuente_entrada = int(tiempo_datos["fuente_entrada"])
    elif entrada_por_defecto is not None:
        tiempo.fuente_entrada = entrada_por_defecto

    return Elemento(
        id=nombre.id,
        nombre=nombre.nombre,
        capa=capa,
        tiempo=tiempo,
        fuente=fuente,
        extension=nombre.extension,
        ancho=int(medio.get("ancho", 0)),
        alto=int(medio.get("alto", 0)),
        tiene_alfa=bool(medio.get("tiene_alfa", False)),
        tiene_audio=bool(medio.get("tiene_audio", capa.codigo.startswith("A"))),
        espacio=transform_desde_datos(datos.get("espacio")),
        animacion=animacion_desde_datos(datos.get("keyframes")),
        efectos=[efecto_desde_datos(e) for e in datos.get("efectos", [])],
        transicion_entrada=transicion_desde_datos(datos.get("transicion_entrada")),
        audio=AudioElemento(
            volumen=float(audio.get("volumen", 1.0)),
            paneo=float(audio.get("paneo", 0.0)),
            silenciado=bool(audio.get("silenciado", False)),
            fundido_entrada=int(audio.get("fundido_entrada", 0)),
            fundido_salida=int(audio.get("fundido_salida", 0)),
        ),
        estado=EstadoElemento(
            activo=bool(estado.get("activo", True)),
            bloqueado=bool(estado.get("bloqueado", False)),
        ),
        texto=texto_desde_datos(datos.get("texto")),
        en_global=en_global,
    )


def extension_de_medio(datos: Datos | None, codigo_capa: str) -> str:
    """Extensión del archivo de medios cuando solo se tiene el gemelo (medio fuera de línea)."""
    if codigo_capa.startswith("T"):
        return "json"
    extension = (datos or {}).get("medio", {}).get("extension")
    if extension:
        return str(extension)
    return "wav" if codigo_capa.startswith("A") else "mp4"


def texto_gemelo(elemento: Elemento) -> str:
    return json_legible(elemento_a_datos(elemento))


def leer_gemelo(ruta: Path) -> Datos | None:
    """Datos del gemelo; None si no existe o está dañado (se rescata con el nombre)."""
    try:
        datos = leer_json(ruta)
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) else None


def escribir_gemelo(ruta: Path, elemento: Elemento) -> None:
    escribir_json_atomico(ruta, elemento_a_datos(elemento))


# --- Shorts ------------------------------------------------------------------------

def short_a_datos(short: Short) -> Datos:
    return {
        "id": short.id,
        "nombre": short.nombre,
        "tiempo": {
            "inicio": Instante(short.inicio).texto(),
            "duracion": Duracion(short.duracion).texto(),
        },
        "ventana": {
            "x": short.ventana.x,
            "zoom": short.ventana.zoom,
            "keyframes": animacion_a_datos(short.ventana.animacion),
        },
    }


def short_desde_datos(datos: Datos | None, nombre: NombreShort) -> Short:
    datos = datos or {}
    ventana = datos.get("ventana", {})
    return Short(
        id=nombre.id,
        nombre=nombre.nombre,
        inicio=nombre.inicio.fotograma,
        duracion=nombre.duracion.fotogramas,
        ventana=VentanaVertical(
            x=float(ventana.get("x", VentanaVertical().x)),
            zoom=float(ventana.get("zoom", 1.0)),
            animacion=animacion_desde_datos(ventana.get("keyframes")),
        ),
    )
