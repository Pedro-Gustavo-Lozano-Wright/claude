"""Punto de entrada único del editor (PROJECT.md, sección 15).

    python main.py                                  interfaz
    python main.py RUTA_PROYECTO                    interfaz con ese proyecto
    python main.py --nuevo RUTA_PROYECTO            crear un proyecto y abrirlo
    python main.py --render RUTA --capitulo 1 [--minutos 00-05]
    python main.py --escanear RUTA_PROYECTO
    python main.py --shorts RUTA --capitulo 1

El main crece por épicas: cada modo avisa qué épica lo completa mientras no
esté implementado.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from editor.core.ajustes import ARCHIVO_ESTANDAR, Ajustes, ruta_config
from editor.core.estandar import CAPITULO_MAXIMO, CAPITULO_MINIMO, MINUTOS_POR_CAPITULO, Estandar
from editor.core.eventos import BusEventos
from editor.core.utiles.registro import configurar_registro, obtener_registro

registro = obtener_registro("editor")

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_PENDIENTE = 2


@dataclass
class Contexto:
    """Lo que el arranque prepara para cualquier modo."""

    ajustes: Ajustes
    estandar_por_defecto: Estandar
    bus: BusEventos


def rango_minutos(texto: str) -> range:
    """'05' → minuto 5; '00-05' → minutos 0 a 5."""
    partes = texto.split("-")
    try:
        numeros = [int(p) for p in partes]
    except ValueError:
        raise argparse.ArgumentTypeError(f"Rango de minutos inválido: {texto!r}") from None
    if len(numeros) == 1:
        numeros.append(numeros[0])
    if len(numeros) != 2:
        raise argparse.ArgumentTypeError(f"Rango de minutos inválido: {texto!r}")
    desde, hasta = numeros
    if not 0 <= desde <= hasta < MINUTOS_POR_CAPITULO:
        raise argparse.ArgumentTypeError(f"Los minutos van de 00 a {MINUTOS_POR_CAPITULO - 1:02d}: {texto!r}")
    return range(desde, hasta + 1)


def numero_capitulo(texto: str) -> int:
    try:
        numero = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Capítulo inválido: {texto!r}") from None
    if not CAPITULO_MINIMO <= numero <= CAPITULO_MAXIMO:
        raise argparse.ArgumentTypeError(f"Los capítulos van de {CAPITULO_MINIMO} a {CAPITULO_MAXIMO}.")
    return numero


def crear_analizador() -> argparse.ArgumentParser:
    analizador = argparse.ArgumentParser(
        prog="main.py",
        description="Editor de video por capítulos de 24 minutos y minutos de 60 s.",
    )
    analizador.add_argument("proyecto", nargs="?", type=Path, help="proyecto que se abre en la interfaz")
    modos = analizador.add_mutually_exclusive_group()
    modos.add_argument("--nuevo", type=Path, metavar="RUTA", help="crear un proyecto y abrirlo")
    modos.add_argument("--render", type=Path, metavar="RUTA", help="renderizar sin interfaz")
    modos.add_argument("--escanear", type=Path, metavar="RUTA", help="reconstruir el modelo desde el disco")
    modos.add_argument("--shorts", type=Path, metavar="RUTA", help="renderizar los Shorts desactualizados")
    modos.add_argument("--fotograma", type=Path, metavar="RUTA", help="exportar un fotograma a PNG")
    analizador.add_argument("--tiempo", help="instante para --fotograma: MM:SS.FF (p. ej. 02:12.08)")
    analizador.add_argument("--salida", type=Path, help="archivo PNG para --fotograma")
    analizador.add_argument("--por-idioma", action="store_true", help="con --render: un archivo por idioma")
    analizador.add_argument("--capitulo", type=numero_capitulo, help="capítulo para --render y --shorts")
    analizador.add_argument("--minutos", type=rango_minutos, help="rango de minutos para --render, p. ej. 00-05")
    analizador.add_argument("--nivel-registro", default=None, help="DEBUG, INFO, WARNING o ERROR")
    return analizador


def validar_argumentos(analizador: argparse.ArgumentParser, argumentos: argparse.Namespace) -> None:
    sin_interfaz = argumentos.render or argumentos.escanear or argumentos.shorts or argumentos.nuevo or argumentos.fotograma
    if sin_interfaz and argumentos.proyecto is not None:
        analizador.error("La ruta del proyecto se indica en el propio modo, no como argumento suelto.")
    if (argumentos.render or argumentos.shorts or argumentos.fotograma) and argumentos.capitulo is None:
        analizador.error("--render, --shorts y --fotograma necesitan --capitulo.")
    if argumentos.fotograma and not argumentos.tiempo:
        analizador.error("--fotograma necesita --tiempo MM:SS.FF.")
    if argumentos.minutos is not None and not argumentos.render:
        analizador.error("--minutos solo se usa con --render.")


def arrancar(argumentos: argparse.Namespace) -> Contexto:
    ajustes = Ajustes.cargar()
    configurar_registro(argumentos.nivel_registro or ajustes.nivel_registro)
    estandar = Estandar.cargar(ruta_config(ARCHIVO_ESTANDAR))
    return Contexto(ajustes=ajustes, estandar_por_defecto=estandar, bus=BusEventos())


def pendiente(modo: str, epica: str) -> int:
    registro.warning("El modo %s todavía no está implementado (épica %s).", modo, epica)
    return SALIDA_PENDIENTE


def modo_nuevo(contexto: Contexto, ruta: Path) -> int:
    """Crea el proyecto con su primer capítulo (cap0001, min00–min23) y lo abre en la interfaz."""
    from editor.core.proyecto_fs import estructura

    try:
        proyecto = estructura.crear_proyecto(ruta, estandar=contexto.estandar_por_defecto)
    except estructura.ProyectoExistente as error:
        registro.error("%s", error)
        return SALIDA_ERROR
    capitulo = estructura.crear_capitulo(proyecto, 1)
    contexto.ajustes.registrar_reciente(ruta)
    contexto.ajustes.guardar_usuario()
    print(f"Proyecto creado en {proyecto.raiz}")
    print(f"  {capitulo.codigo}/ con min00 … min23, global/, render/ y shorts/")
    print("  brutos/, taller/, recursos/ y _proyecto.json")
    return modo_interfaz(contexto, ruta)


def modo_escanear(contexto: Contexto, ruta: Path) -> int:
    """Lee el proyecto completo en solo lectura y muestra lo encontrado."""
    from editor.core.proyecto_fs.diario import Diario
    from editor.core.proyecto_fs.escaner import NoEsProyecto, abrir_proyecto

    try:
        apertura = abrir_proyecto(ruta, solo_lectura=True)
    except NoEsProyecto as error:
        registro.error("%s", error)
        return SALIDA_ERROR
    proyecto = apertura.proyecto
    for numero in proyecto.numeros_capitulos():
        proyecto.capitulo(numero)
    print(f"Proyecto: {proyecto.nombre} ({proyecto.raiz})")
    print(f"Idiomas: {', '.join(proyecto.idiomas)} · Brutos: {len(proyecto.taller.brutos)} · "
          f"Piezas: {len(proyecto.taller.piezas)}")
    print(apertura.informe.resumen())
    if Diario(proyecto.raiz).hay_pendiente():
        print("Hay un guardado interrumpido: se completará al abrir el proyecto para editar.")
    return SALIDA_OK


def _abrir_para_servicio(ruta: Path):
    from editor.core.proyecto_fs.bloqueo import ProyectoBloqueado
    from editor.core.proyecto_fs.escaner import NoEsProyecto, abrir_proyecto

    try:
        return abrir_proyecto(ruta)
    except (NoEsProyecto, ProyectoBloqueado) as error:
        registro.error("%s", error)
        return None


def _progreso_en_consola(contexto: Contexto) -> None:
    from editor.core.eventos import TareaProgreso

    ultimo = {"texto": ""}

    def mostrar(evento: TareaProgreso) -> None:
        texto = f"{evento.descripcion} {round(evento.fraccion * 100):3d} %"
        if texto != ultimo["texto"]:
            ultimo["texto"] = texto
            print(f"\r{texto:<60}", end="", flush=True)

    contexto.bus.suscribir(TareaProgreso, mostrar)


def modo_render(contexto: Contexto, ruta: Path, capitulo: int, minutos: range | None, por_idioma: bool = False) -> int:
    from editor.core.servicios import render
    from editor.core.tareas.cola import ejecutar_ahora

    apertura = _abrir_para_servicio(ruta)
    if apertura is None:
        return SALIDA_ERROR
    try:
        proyecto = apertura.proyecto
        if not proyecto.existe_capitulo(capitulo):
            registro.error("No existe el capítulo %d.", capitulo)
            return SALIDA_ERROR
        desde = None if minutos is None else minutos.start
        hasta = None if minutos is None else minutos.stop - 1
        pedido = render.PedidoRender.crear(
            proyecto, capitulo, desde, hasta, modo=render.ARCHIVOS if por_idioma else render.PISTAS
        )
        _progreso_en_consola(contexto)
        resultado = ejecutar_ahora(lambda c: render.renderizar(pedido, c), "render", contexto.bus)
        render.registrar(proyecto, apertura.estado, resultado, contexto.bus)
        print()
        for archivo in resultado.archivos:
            print(f"Render: {archivo}")
        return SALIDA_OK
    finally:
        apertura.cerrar()


def modo_fotograma(contexto: Contexto, ruta: Path, capitulo: int, tiempo: str, salida: Path | None) -> int:
    import re

    from PIL import Image

    from editor.core.motor.compositor import FINAL, Compositor
    from editor.core.motor.decodificador import GestorFuentes
    from editor.core.proyecto_fs.escaner import NoEsProyecto, abrir_proyecto
    from editor.core.servicios.fuentes import ResolutorFuentes
    from editor.core.tiempo.granularidad import componer

    coincidencia = re.fullmatch(r"(\d{1,2}):(\d{2})\.(\d{2})", tiempo)
    if coincidencia is None:
        registro.error("Tiempo inválido: %s (formato MM:SS.FF)", tiempo)
        return SALIDA_ERROR
    f = componer(*(int(g) for g in coincidencia.groups()))
    try:
        apertura = abrir_proyecto(ruta, solo_lectura=True)
    except NoEsProyecto as error:
        registro.error("%s", error)
        return SALIDA_ERROR
    proyecto = apertura.proyecto
    compositor = Compositor(GestorFuentes(), ResolutorFuentes.desde(proyecto), proyecto.raiz / "recursos", FINAL)
    imagen = compositor.componer(proyecto.capitulo(capitulo), f, (proyecto.estandar.lienzo_ancho, proyecto.estandar.lienzo_alto))
    destino = salida or Path(f"cap{capitulo:04d}_{tiempo.replace(':', '').replace('.', 'f')}.png")
    Image.fromarray(imagen).save(destino)
    print(f"Fotograma: {destino}")
    return SALIDA_OK


def modo_shorts(contexto: Contexto, ruta: Path, capitulo: int) -> int:
    return pendiente(f"--shorts {ruta} (capítulo {capitulo})", "E22")


def modo_interfaz(contexto: Contexto, ruta: Path | None) -> int:
    """Ventana de escritorio de Flet (E12–E16). Sin ruta: el último proyecto o la pantalla de inicio."""
    try:
        from editor.app.aplicacion import lanzar
    except ImportError as error:
        registro.error("No se pudo cargar la interfaz (%s). Instale las dependencias: pip install -r requirements.txt", error)
        return SALIDA_ERROR
    if ruta is not None and not ruta.exists():
        registro.error("No existe la carpeta del proyecto: %s", ruta)
        return SALIDA_ERROR
    lanzar(contexto.ajustes, contexto.bus, contexto.estandar_por_defecto, ruta)
    return SALIDA_OK


def main(argv: list[str] | None = None) -> int:
    analizador = crear_analizador()
    argumentos = analizador.parse_args(argv)
    validar_argumentos(analizador, argumentos)
    contexto = arrancar(argumentos)
    registro.debug("Estándar por defecto: %s", contexto.estandar_por_defecto)

    if argumentos.nuevo:
        return modo_nuevo(contexto, argumentos.nuevo)
    if argumentos.escanear:
        return modo_escanear(contexto, argumentos.escanear)
    if argumentos.render:
        return modo_render(contexto, argumentos.render, argumentos.capitulo, argumentos.minutos, argumentos.por_idioma)
    if argumentos.fotograma:
        return modo_fotograma(contexto, argumentos.fotograma, argumentos.capitulo, argumentos.tiempo, argumentos.salida)
    if argumentos.shorts:
        return modo_shorts(contexto, argumentos.shorts, argumentos.capitulo)
    return modo_interfaz(contexto, argumentos.proyecto)


if __name__ == "__main__":
    sys.exit(main())
