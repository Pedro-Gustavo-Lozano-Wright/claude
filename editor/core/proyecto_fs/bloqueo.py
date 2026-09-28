"""Bloqueo del proyecto: una sola instancia puede editarlo a la vez (T5.5).

El archivo `.bloqueo` guarda PID, equipo y fecha. Si lo tiene otro proceso
vivo, la segunda instancia abre en solo lectura. Si el proceso ya no existe
(cierre inesperado), el bloqueo es huérfano y se recupera.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from editor.core.tiempo.nomenclatura import ARCHIVO_BLOQUEO


@dataclass(frozen=True)
class InfoBloqueo:
    pid: int
    equipo: str
    fecha: str

    def vigente(self) -> bool:
        """True si el proceso que lo tomó sigue vivo (o está en otro equipo: no se puede saber)."""
        if self.equipo != socket.gethostname():
            return True
        if self.pid == os.getpid():
            return True  # este mismo proceso ya lo tiene abierto
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


class ProyectoBloqueado(RuntimeError):
    def __init__(self, info: InfoBloqueo) -> None:
        super().__init__(f"El proyecto está abierto en {info.equipo} (PID {info.pid}) desde {info.fecha}.")
        self.info = info


def leer_bloqueo(raiz: Path) -> InfoBloqueo | None:
    ruta = raiz / ARCHIVO_BLOQUEO
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return InfoBloqueo(int(datos["pid"]), str(datos["equipo"]), str(datos["fecha"]))
    except (OSError, ValueError, KeyError):
        return None


class Bloqueo:
    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        self.adquirido = False
        self.huerfano_recuperado: InfoBloqueo | None = None

    @property
    def ruta(self) -> Path:
        return self.raiz / ARCHIVO_BLOQUEO

    def adquirir(self) -> None:
        """Toma el bloqueo. Lanza ProyectoBloqueado si otra instancia viva lo tiene."""
        existente = leer_bloqueo(self.raiz)
        if existente is not None:
            if existente.vigente():
                raise ProyectoBloqueado(existente)
            self.huerfano_recuperado = existente
            self.ruta.unlink(missing_ok=True)
        info = {
            "pid": os.getpid(),
            "equipo": socket.gethostname(),
            "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        try:
            descriptor = os.open(self.ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            otro = leer_bloqueo(self.raiz)
            raise ProyectoBloqueado(otro or InfoBloqueo(-1, "?", "?")) from None
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            json.dump(info, archivo)
        self.adquirido = True

    def liberar(self) -> None:
        if self.adquirido:
            actual = leer_bloqueo(self.raiz)
            if actual is not None and actual.pid == os.getpid():
                self.ruta.unlink(missing_ok=True)
            self.adquirido = False

    def __enter__(self) -> "Bloqueo":
        self.adquirir()
        return self

    def __exit__(self, *_: object) -> None:
        self.liberar()
