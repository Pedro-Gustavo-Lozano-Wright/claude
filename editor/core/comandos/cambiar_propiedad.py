"""Cambiar una propiedad cualquiera de un Elemento por su ruta.

Rutas con puntos sobre el Elemento, por ejemplo:
    "nombre", "espacio.x", "espacio.opacidad", "audio.volumen",
    "estado.bloqueado", "texto.texto", "texto.estilo.tamano".

Funciona con partes inmutables (Transform, EstiloTexto): las reconstruye con
el valor nuevo. Los valores son absolutos, así que los arrastres de un
deslizador se fusionan.
"""

from __future__ import annotations

import math
from dataclasses import fields, is_dataclass, replace
from typing import Any

from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto
from editor.core.tiempo.nomenclatura import es_nombre_valido

# Rutas que no se cambian por aquí: tienen su propio comando con reglas.
RUTAS_RESERVADAS = {"id", "capa", "tiempo.inicio", "tiempo.duracion", "en_global", "fuente", "archivo"}


def _con_valor(objeto: Any, partes: list[str], valor: Any) -> Any:
    """Devuelve `objeto` con el atributo de la ruta cambiado (reconstruye lo inmutable)."""
    nombre = partes[0]
    if not is_dataclass(objeto) or nombre not in {f.name for f in fields(objeto)}:
        raise EdicionRechazada(f"Propiedad desconocida: {nombre!r}")
    nuevo_valor = valor if len(partes) == 1 else _con_valor(getattr(objeto, nombre), partes[1:], valor)
    if getattr(type(objeto), "__dataclass_params__").frozen:
        return replace(objeto, **{nombre: nuevo_valor})
    setattr(objeto, nombre, nuevo_valor)
    return objeto


def leer_ruta(objeto: Any, ruta: str) -> Any:
    for parte in ruta.split("."):
        objeto = getattr(objeto, parte)
    return objeto


class CambiarPropiedad(EdicionCapitulo):
    descripcion = "Cambiar propiedad"

    def __init__(self, capitulo: int, id_elemento: str, ruta: str, valor: Any) -> None:
        super().__init__(capitulo)
        if ruta in RUTAS_RESERVADAS or ruta.startswith(("tiempo.inicio", "tiempo.duracion")):
            raise ValueError(f"La propiedad {ruta!r} se cambia con su comando específico.")
        self.id_elemento = id_elemento
        self.ruta = ruta
        self.valor = valor
        self.descripcion = f"Cambiar {ruta}"

    def clave_fusion(self) -> tuple | None:
        return ("propiedad", self.id_elemento, self.ruta)

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        # "estado.bloqueado" debe poder desbloquear: no se exige que sea editable.
        elemento = self.obtener(capitulo, self.id_elemento, editable=self.ruta != "estado.bloqueado")
        if self.ruta == "nombre" and not es_nombre_valido(str(self.valor)):
            raise EdicionRechazada("Nombre descriptivo inválido: minúsculas, números y guiones.")
        self.retirar(capitulo, [elemento])
        _con_valor(elemento, self.ruta.split("."), self.valor)
        self.colocar(capitulo, [elemento])
        return set()


class CambiarVelocidad(EdicionCapitulo):
    """Cambia la velocidad. Por defecto conserva el contenido (la duración se ajusta)."""

    descripcion = "Cambiar velocidad"

    def __init__(self, capitulo: int, id_elemento: str, velocidad: float, conservar_contenido: bool = True) -> None:
        super().__init__(capitulo)
        if velocidad == 0:
            raise ValueError("La velocidad no puede ser cero.")
        self.id_elemento = id_elemento
        self.velocidad = velocidad
        self.conservar_contenido = conservar_contenido

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        if elemento.tiempo.congelado:
            raise EdicionRechazada("Un fotograma congelado no tiene velocidad.")
        self.retirar(capitulo, [elemento])
        if self.conservar_contenido:
            usados = elemento.tiempo.fotogramas_fuente_usados
            elemento.tiempo.duracion = max(1, math.ceil(usados / abs(self.velocidad)))
        elemento.tiempo.velocidad = self.velocidad
        self.colocar(capitulo, [elemento])
        return set()
