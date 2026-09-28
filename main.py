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
    analizador.add_argument("--capitulo", type=numero_capitulo, help="capítulo para --render y --shorts")
    analizador.add_argument("--minutos", type=rango_minutos, help="rango de minutos para --render, p. ej. 00-05")
    analizador.add_argument("--nivel-registro", default=None, help="DEBUG, INFO, WARNING o ERROR")
    return analizador


def validar_argumentos(analizador: argparse.ArgumentParser, argumentos: argparse.Namespace) -> None:
    sin_interfaz = argumentos.render or argumentos.escanear or argumentos.shorts or argumentos.nuevo
    if sin_interfaz and argumentos.proyecto is not None:
        analizador.error("La ruta del proyecto se indica en el propio modo, no como argumento suelto.")
    if (argumentos.render or argumentos.shorts) and argumentos.capitulo is None:
        analizador.error("--render y --shorts necesitan --capitulo.")
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
    return pendiente(f"--nuevo {ruta}", "E5")


def modo_escanear(contexto: Contexto, ruta: Path) -> int:
    return pendiente(f"--escanear {ruta}", "E5")


def modo_render(contexto: Contexto, ruta: Path, capitulo: int, minutos: range | None) -> int:
    alcance = "capítulo completo" if minutos is None else f"minutos {minutos.start:02d}-{minutos.stop - 1:02d}"
    return pendiente(f"--render {ruta} (capítulo {capitulo}, {alcance})", "E10")


def modo_shorts(contexto: Contexto, ruta: Path, capitulo: int) -> int:
    return pendiente(f"--shorts {ruta} (capítulo {capitulo})", "E20")


def modo_interfaz(contexto: Contexto, ruta: Path | None) -> int:
    return pendiente("interfaz" + (f" con {ruta}" if ruta else ""), "E12")


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
        return modo_render(contexto, argumentos.render, argumentos.capitulo, argumentos.minutos)
    if argumentos.shorts:
        return modo_shorts(contexto, argumentos.shorts, argumentos.capitulo)
    return modo_interfaz(contexto, argumentos.proyecto)


if __name__ == "__main__":
    sys.exit(main())
