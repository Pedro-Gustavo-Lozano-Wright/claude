"""Proyecto: raíz del modelo. Hasta 1000 capítulos, el Taller y el estándar propio."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from editor.core.estandar import CAPITULO_MAXIMO, CAPITULO_MINIMO, Estandar
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.errores import ErrorModelo, NoEncontrado
from editor.core.modelo.referencias import IndiceReferencias
from editor.core.modelo.taller import Taller
from editor.core.tiempo.nomenclatura import GeneradorIds, normalizar_nombre, validar_numero_capitulo


@dataclass
class Proyecto:
    nombre: str
    raiz: Path | None = None
    estandar: Estandar = field(default_factory=Estandar)
    taller: Taller = field(default_factory=Taller)
    capitulos: dict[int, Capitulo] = field(default_factory=dict)
    ids: GeneradorIds = field(default_factory=GeneradorIds)
    referencias: IndiceReferencias = field(default_factory=IndiceReferencias)

    # --- IDs ---------------------------------------------------------------------

    def nuevo_id(self) -> str:
        return self.ids.nuevo()

    def registrar_ids_existentes(self) -> None:
        """Reserva todos los IDs presentes en el modelo (tras cargarlo desde disco)."""
        for bruto in self.taller.brutos.values():
            self.ids.registrar(bruto.id)
        for pieza in self.taller.piezas.values():
            self.ids.registrar(pieza.id)
        for capitulo in self.capitulos.values():
            for elemento in capitulo.todos_los_elementos():
                self.ids.registrar(elemento.id)
            for short in capitulo.shorts.values():
                self.ids.registrar(short.id)

    # --- Capítulos ---------------------------------------------------------------

    def siguiente_numero_capitulo(self) -> int:
        for numero in range(CAPITULO_MINIMO, CAPITULO_MAXIMO + 1):
            if numero not in self.capitulos:
                return numero
        raise ErrorModelo(f"El proyecto ya tiene {CAPITULO_MAXIMO} capítulos.")

    def crear_capitulo(self, numero: int | None = None, titulo: str = "") -> Capitulo:
        numero = self.siguiente_numero_capitulo() if numero is None else numero
        validar_numero_capitulo(numero)
        if numero in self.capitulos:
            raise ErrorModelo(f"Ya existe el capítulo {numero}.")
        capitulo = Capitulo(numero=numero, titulo=titulo)
        self.capitulos[numero] = capitulo
        return capitulo

    def capitulo(self, numero: int) -> Capitulo:
        try:
            return self.capitulos[numero]
        except KeyError:
            raise NoEncontrado(f"No existe el capítulo {numero}.") from None

    def capitulos_ordenados(self) -> list[Capitulo]:
        return [self.capitulos[n] for n in sorted(self.capitulos)]

    # --- Búsquedas ---------------------------------------------------------------

    def buscar_elemento(self, id_elemento: str) -> tuple[Capitulo, Elemento] | None:
        ubicacion = self.referencias.ubicacion(id_elemento)
        if ubicacion is not None and ubicacion.capitulo in self.capitulos:
            capitulo = self.capitulos[ubicacion.capitulo]
            elemento = capitulo.buscar(id_elemento)
            if elemento is not None:
                return capitulo, elemento
        for capitulo in self.capitulos.values():
            elemento = capitulo.buscar(id_elemento)
            if elemento is not None:
                return capitulo, elemento
        return None

    def reconstruir_referencias(self) -> None:
        self.referencias.reconstruir(self)

    @property
    def nombre_carpeta(self) -> str:
        return normalizar_nombre(self.nombre)
