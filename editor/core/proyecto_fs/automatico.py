"""Estado automático: lo que producen los servicios, escrito en el momento.

Separado de lo que edita el usuario (PROJECT.md, 22.7):

| Archivo | Contenido | Lo escribe |
|---|---|---|
| `capNNNN/render/_renders.json` | Entregables, último render de cada minuto y de cada Short | Servicio de render (E10, E22) |
| `taller/pieNNNN…/_horneado.json` | Resultado del último horneado | Servicio de horneado (E9) |

Así un render o un horneado nunca se pierde por cerrar sin guardar, y
escribirlo nunca persiste ediciones que el usuario no guardó. Cada escritura
actualiza el estado conocido del disco para que el siguiente guardado no la
confunda con un cambio externo.
"""

from __future__ import annotations

from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.pieza import Pieza
from editor.core.modelo.proyecto import Proyecto
from editor.core.proyecto_fs import estructura
from editor.core.proyecto_fs.estado_disco import EstadoDisco, Firma, RegistroArchivo
from editor.core.proyecto_fs.manifiestos import horneado_a_datos, renders_a_datos
from editor.core.proyecto_fs.serializacion import escribir_json_atomico, huella


def anotar_renders(proyecto: Proyecto, estado: EstadoDisco, numero: int, entregables: list[tuple[str, str]] = (),
                   minutos: dict[int, str] | None = None, shorts: dict[str, tuple[int, str]] | None = None) -> None:
    """Anota un render terminado: `entregables` (archivo, huella), `minutos` (minuto → huella de video,
    la versión se incrementa) y `shorts` (id → (versión, huella)).

    Si el capítulo no está en memoria (el usuario cambió de capítulo mientras se renderizaba),
    se actualiza `_renders.json` en disco sin cargarlo: solo hay un capítulo en memoria.
    """
    from editor.core.modelo.capitulo import RegistroRender
    from editor.core.modelo.minuto import RegistroRenderMinuto
    from editor.core.modelo.short import RegistroRenderShort
    from editor.core.proyecto_fs.serializacion import leer_json
    from editor.core.tiempo.nomenclatura import NombreRender, VERSION_ESQUEMA

    minutos = minutos or {}
    shorts = shorts or {}
    capitulo = proyecto.capitulos.get(numero)
    if capitulo is not None:
        for archivo, marca in entregables:
            capitulo.renders.append(RegistroRender(NombreRender.desde_archivo(archivo), marca))
        for n, marca in minutos.items():
            minuto = capitulo.minuto(n)
            minuto.ultimo_render = RegistroRenderMinuto(minuto.siguiente_version_render, marca)
        for id_short, (version, marca) in shorts.items():
            if id_short in capitulo.shorts:
                capitulo.shorts[id_short].ultimo_render = RegistroRenderShort(version, marca)
        guardar_renders(proyecto, estado, capitulo)
        return
    assert proyecto.raiz is not None
    ruta = estructura.ruta_renders(proyecto.raiz, numero)
    datos = (leer_json(ruta) if ruta.exists() else None) or {"version_esquema": VERSION_ESQUEMA}
    datos.setdefault("entregables", []).extend({"archivo": a, "huella": m} for a, m in entregables)
    registro_minutos = datos.setdefault("minutos", {})
    for n, marca in minutos.items():
        anterior = registro_minutos.get(f"{n:02d}", {}).get("version", 0)
        registro_minutos[f"{n:02d}"] = {"version": int(anterior) + 1, "huella": marca}
    datos.setdefault("shorts", {}).update({i: {"version": v, "huella": m} for i, (v, m) in shorts.items()})
    escribir_json_atomico(ruta, datos)
    relativa = estructura.relativa(proyecto.raiz, ruta)
    estado.capitulo(numero).control[relativa] = RegistroArchivo(relativa, Firma.de(ruta), huella(datos))


def guardar_renders(proyecto: Proyecto, estado: EstadoDisco, capitulo: Capitulo) -> None:
    assert proyecto.raiz is not None
    ruta = estructura.ruta_renders(proyecto.raiz, capitulo.numero)
    datos = renders_a_datos(capitulo)
    escribir_json_atomico(ruta, datos)
    relativa = estructura.relativa(proyecto.raiz, ruta)
    estado.capitulo(capitulo.numero).control[relativa] = RegistroArchivo(relativa, Firma.de(ruta), huella(datos))


def guardar_horneado(proyecto: Proyecto, estado: EstadoDisco, pieza: Pieza) -> None:
    assert proyecto.raiz is not None
    ruta = estructura.ruta_manifiesto_horneado(proyecto.raiz, pieza)
    datos = horneado_a_datos(pieza.horneado)
    escribir_json_atomico(ruta, datos)
    estado.horneados[pieza.id] = RegistroArchivo(estructura.relativa(proyecto.raiz, ruta), Firma.de(ruta), huella(datos))
