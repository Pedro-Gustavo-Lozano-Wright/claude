"""Ajustes de la aplicación (no del proyecto).

Los valores por defecto viven en `config/` del repositorio. El usuario puede
sobrescribirlos en `~/.config/editor/`; ese directorio también guarda los
proyectos recientes y la distribución de paneles.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
CONFIG_REPOSITORIO = RAIZ_REPOSITORIO / "config"
CONFIG_USUARIO = Path.home() / ".config" / "editor"

ARCHIVO_AJUSTES = "ajustes.json"
ARCHIVO_ESTANDAR = "estandar.json"
ARCHIVO_DISTRIBUCION = "distribucion.json"
ARCHIVO_ATAJOS = "atajos.json"


@dataclass
class Ajustes:
    cache_fotogramas_mb: int = 512
    autosave_segundos: int = 120
    historial_pasos: int = 100
    vista_previa_fps: int = 12
    vista_previa_calidad_jpeg: int = 80
    monitor_calidad_pausa_jpeg: int = 90
    trabajadores_fondo: int = 2
    nivel_registro: str = "INFO"
    proyectos_recientes: list[str] = field(default_factory=list)
    maximo_recientes: int = 10

    @classmethod
    def cargar(cls) -> "Ajustes":
        """Combina los valores del repositorio con los del usuario."""
        datos: dict[str, Any] = {}
        for ruta in (CONFIG_REPOSITORIO / ARCHIVO_AJUSTES, CONFIG_USUARIO / ARCHIVO_AJUSTES):
            datos.update(leer_json(ruta))
        nombres = {f.name for f in fields(cls)}
        return cls(**{clave: valor for clave, valor in datos.items() if clave in nombres})

    def guardar_usuario(self) -> None:
        CONFIG_USUARIO.mkdir(parents=True, exist_ok=True)
        escribir_json(CONFIG_USUARIO / ARCHIVO_AJUSTES, asdict(self))

    def registrar_reciente(self, ruta_proyecto: Path) -> None:
        texto = str(ruta_proyecto.resolve())
        if texto in self.proyectos_recientes:
            self.proyectos_recientes.remove(texto)
        self.proyectos_recientes.insert(0, texto)
        del self.proyectos_recientes[self.maximo_recientes:]


def ruta_config(nombre: str) -> Path:
    """Ruta efectiva de un archivo de configuración: la del usuario si existe."""
    usuario = CONFIG_USUARIO / nombre
    return usuario if usuario.exists() else CONFIG_REPOSITORIO / nombre


def leer_json(ruta: Path) -> dict[str, Any]:
    if not ruta.exists():
        return {}
    with ruta.open(encoding="utf-8") as archivo:
        datos = json.load(archivo)
    return datos if isinstance(datos, dict) else {}


def escribir_json(ruta: Path, datos: dict[str, Any]) -> None:
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
