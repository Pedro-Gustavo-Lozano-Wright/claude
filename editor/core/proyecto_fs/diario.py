"""Diario de operaciones de disco (T5.7).

Un guardado es una secuencia de operaciones. Antes de tocar nada se escribe el
plan completo en `.diario/plan.json`; después se ejecuta paso a paso,
registrando el avance en `.diario/progreso`. Si el programa se corta, al
reabrir el proyecto el plan se **completa** desde donde quedó.

Todas las operaciones son idempotentes, así que repetir un paso ya hecho no
causa daño:

- `carpeta`: crea una carpeta.
- `mover`: mueve un archivo (si el origen ya no está y el destino sí, ya se hizo).
- `copiar`: copia a un temporal y lo reemplaza de una vez.

Las escrituras (gemelos, manifiestos, guiones) se preparan antes como archivos
en `.diario/preparados/` y el plan las mueve a su lugar: así también son
atómicas.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from editor.core.proyecto_fs.serializacion import escribir_json_atomico, escribir_texto_atomico
from editor.core.tiempo.nomenclatura import CARPETA_DIARIO

registro = logging.getLogger(__name__)

CARPETA = "carpeta"
MOVER = "mover"
COPIAR = "copiar"


@dataclass(frozen=True)
class Operacion:
    tipo: str
    destino: str          # relativa a la raíz
    origen: str = ""      # relativa a la raíz (vacía para `carpeta`)


class ErrorDiario(RuntimeError):
    pass


class Diario:
    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        self.carpeta = raiz / CARPETA_DIARIO
        self.preparados = self.carpeta / "preparados"
        self.temporales = self.carpeta / "temporales"

    @property
    def ruta_plan(self) -> Path:
        return self.carpeta / "plan.json"

    @property
    def ruta_progreso(self) -> Path:
        return self.carpeta / "progreso"

    def hay_pendiente(self) -> bool:
        return self.ruta_plan.exists()

    # --- Preparación -----------------------------------------------------------

    def limpiar_restos(self) -> None:
        """Borra preparados y temporales de un intento anterior que no llegó a escribir su plan."""
        if self.hay_pendiente():
            return
        for carpeta in (self.preparados, self.temporales):
            if carpeta.exists():
                shutil.rmtree(carpeta, ignore_errors=True)

    def preparar_texto(self, nombre: str, texto: str) -> str:
        """Escribe un archivo preparado y devuelve su ruta relativa para una operación `mover`."""
        ruta = self.preparados / nombre
        escribir_texto_atomico(ruta, texto)
        return ruta.relative_to(self.raiz).as_posix()

    def ruta_temporal(self, nombre: str) -> str:
        return (self.temporales / nombre).relative_to(self.raiz).as_posix()

    # --- Ejecución ---------------------------------------------------------------

    def ejecutar(self, operaciones: list[Operacion]) -> list[str]:
        """Aplica el plan. Devuelve los pasos que fallaron (los demás se aplicaron)."""
        if self.hay_pendiente():
            raise ErrorDiario("Hay un plan anterior sin completar; hay que recuperarlo primero.")
        self.carpeta.mkdir(parents=True, exist_ok=True)
        escribir_json_atomico(self.ruta_plan, [asdict(op) for op in operaciones])
        self._escribir_progreso(0)
        return self._continuar(operaciones, 0)

    def recuperar(self) -> int:
        """Completa un plan interrumpido. Devuelve cuántas operaciones quedaban."""
        if not self.hay_pendiente():
            return 0
        operaciones = [Operacion(**datos) for datos in json.loads(self.ruta_plan.read_text(encoding="utf-8"))]
        try:
            hechas = int(self.ruta_progreso.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            hechas = 0
        restantes = len(operaciones) - hechas
        registro.warning("Recuperando un guardado interrumpido: %d operaciones pendientes.", restantes)
        self._continuar(operaciones, hechas)
        return restantes

    def _continuar(self, operaciones: list[Operacion], desde: int) -> list[str]:
        """Un paso que no se puede completar se registra y se sigue con el resto.

        Así un plan nunca queda trabado para siempre; lo que falló aparece como
        medio fuera de línea o conflicto en el siguiente escaneo.
        """
        errores: list[str] = []
        for indice in range(desde, len(operaciones)):
            try:
                self._aplicar(operaciones[indice])
            except (ErrorDiario, OSError) as error:
                registro.error("Paso %d del guardado falló: %s", indice, error)
                errores.append(str(error))
            self._escribir_progreso(indice + 1)
        self._terminar()
        return errores

    def _aplicar(self, op: Operacion) -> None:
        destino = self.raiz / op.destino
        if op.tipo == CARPETA:
            destino.mkdir(parents=True, exist_ok=True)
            return
        origen = self.raiz / op.origen
        destino.parent.mkdir(parents=True, exist_ok=True)
        if op.tipo == MOVER:
            if origen.exists():
                os.replace(origen, destino)
            elif not destino.exists():
                raise ErrorDiario(f"No se puede mover {op.origen}: no existe ni está en su destino.")
            return
        if op.tipo == COPIAR:
            if not origen.exists():
                raise ErrorDiario(f"No se puede copiar {op.origen}: no existe.")
            parcial = destino.with_name(destino.name + ".parcial")
            shutil.copy2(origen, parcial)
            os.replace(parcial, destino)
            return
        raise ErrorDiario(f"Operación desconocida: {op.tipo}")

    def _escribir_progreso(self, hechas: int) -> None:
        with self.ruta_progreso.open("w", encoding="utf-8") as archivo:
            archivo.write(str(hechas))
            archivo.flush()
            os.fsync(archivo.fileno())

    def _terminar(self) -> None:
        self.ruta_plan.unlink(missing_ok=True)
        self.ruta_progreso.unlink(missing_ok=True)
        for carpeta in (self.preparados, self.temporales):
            if carpeta.exists():
                shutil.rmtree(carpeta, ignore_errors=True)
