"""Errores del modelo."""

from __future__ import annotations


class ErrorModelo(ValueError):
    """Operación que rompería una regla del modelo."""


class Solapamiento(ErrorModelo):
    """Dos Elementos ocuparían la misma capa al mismo tiempo."""

    def __init__(self, id_nuevo: str, id_existente: str, capa: str) -> None:
        super().__init__(f"El Elemento {id_nuevo} se solapa con {id_existente} en la capa {capa}.")
        self.id_nuevo = id_nuevo
        self.id_existente = id_existente
        self.capa = capa


class NoEncontrado(ErrorModelo, KeyError):
    """No existe un objeto con ese ID."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else "No encontrado"
