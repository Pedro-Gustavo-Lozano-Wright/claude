"""Proyecto: raíz del modelo. Hasta 1000 capítulos, el Taller y el estándar propio.

Los capítulos se cargan **bajo demanda**: el proyecto conoce qué capítulos
existen (`indice_capitulos`) y pide cada uno a un cargador inyectado por
`proyecto_fs` cuando se necesita. Así el modelo no depende del disco
 y abrir un proyecto con 1000 capítulos es inmediato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from editor.core.estandar import CAPITULO_MAXIMO, CAPITULO_MINIMO, Estandar
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.errores import ErrorModelo, NoEncontrado
from editor.core.modelo.referencias import IndiceReferencias
from editor.core.modelo.taller import Taller
from editor.core.tiempo.nomenclatura import GeneradorIds, normalizar_nombre, validar_numero_capitulo

CargadorCapitulo = Callable[[int], Capitulo]


@dataclass
class Proyecto:
    nombre: str
    raiz: Path | None = None
    estandar: Estandar = field(default_factory=Estandar)
    taller: Taller = field(default_factory=Taller)
    # Capítulos que existen (en disco o recién creados): número → título.
    indice_capitulos: dict[int, str] = field(default_factory=dict)
    # Capítulos cargados en memoria.
    capitulos: dict[int, Capitulo] = field(default_factory=dict)
    ids: GeneradorIds = field(default_factory=GeneradorIds)
    referencias: IndiceReferencias = field(default_factory=IndiceReferencias)
    # Idiomas del proyecto (ISO 639-1). El primero es el principal: el de la vista
    # previa y el del render por defecto.
    idiomas: list[str] = field(default_factory=lambda: ["es"])
    cargador_capitulo: CargadorCapitulo | None = field(default=None, repr=False, compare=False)

    # --- IDs ---------------------------------------------------------------------

    def nuevo_id(self) -> str:
        return self.ids.nuevo()

    def registrar_ids_cargados(self) -> None:
        """Reserva los IDs presentes en lo cargado en memoria.

        Los IDs de capítulos sin cargar se reservan desde `_proyecto.json`.
        """
        for bruto in self.taller.brutos.values():
            self.ids.registrar(bruto.id)
        for pieza in self.taller.piezas.values():
            self.ids.registrar(pieza.id)
        for capitulo in self.capitulos.values():
            self._registrar_ids_capitulo(capitulo)

    def _registrar_ids_capitulo(self, capitulo: Capitulo) -> None:
        for elemento in capitulo.todos_los_elementos():
            self.ids.registrar(elemento.id)
        for short in capitulo.shorts.values():
            self.ids.registrar(short.id)

    # --- Capítulos ---------------------------------------------------------------

    def existe_capitulo(self, numero: int) -> bool:
        return numero in self.indice_capitulos

    def numeros_capitulos(self) -> list[int]:
        return sorted(self.indice_capitulos)

    def siguiente_numero_capitulo(self) -> int:
        for numero in range(CAPITULO_MINIMO, CAPITULO_MAXIMO + 1):
            if numero not in self.indice_capitulos:
                return numero
        raise ErrorModelo(f"El proyecto ya tiene {CAPITULO_MAXIMO} capítulos.")

    def crear_capitulo(self, numero: int | None = None, titulo: str = "") -> Capitulo:
        numero = self.siguiente_numero_capitulo() if numero is None else numero
        validar_numero_capitulo(numero)
        if numero in self.indice_capitulos:
            raise ErrorModelo(f"Ya existe el capítulo {numero}.")
        capitulo = Capitulo(numero=numero, titulo=titulo)
        self.capitulos[numero] = capitulo
        self.indice_capitulos[numero] = titulo
        return capitulo

    def capitulo(self, numero: int) -> Capitulo:
        """Capítulo en memoria; si existe pero no está cargado, lo carga."""
        if numero in self.capitulos:
            return self.capitulos[numero]
        if numero not in self.indice_capitulos:
            raise NoEncontrado(f"No existe el capítulo {numero}.")
        if self.cargador_capitulo is None:
            raise ErrorModelo(f"El capítulo {numero} no está cargado y no hay cargador disponible.")
        capitulo = self.cargador_capitulo(numero)
        self.capitulos[numero] = capitulo
        self._registrar_ids_capitulo(capitulo)
        for elemento in capitulo.todos_los_elementos():
            self.referencias.registrar(elemento, numero)
        return capitulo

    def descargar_capitulo(self, numero: int) -> None:
        """Libera un capítulo de la memoria (solo si no tiene cambios sin guardar; lo decide quien llama).

        Sus Elementos salen también del índice de referencias: lo que usa un capítulo no
        cargado se consulta en disco (`proyecto_fs.consultas`).
        """
        capitulo = self.capitulos.pop(numero, None)
        if capitulo is not None:
            for elemento in capitulo.todos_los_elementos():
                self.referencias.olvidar(elemento.id)

    def capitulos_cargados(self) -> list[Capitulo]:
        return [self.capitulos[n] for n in sorted(self.capitulos)]

    # --- Búsquedas ---------------------------------------------------------------

    def buscar_elemento(self, id_elemento: str) -> tuple[Capitulo, Elemento] | None:
        """Busca primero por el índice de referencias; después en lo cargado."""
        ubicacion = self.referencias.ubicacion(id_elemento)
        if ubicacion is not None and self.existe_capitulo(ubicacion.capitulo):
            capitulo = self.capitulo(ubicacion.capitulo)
            elemento = capitulo.buscar(id_elemento)
            if elemento is not None:
                return capitulo, elemento
        for capitulo in self.capitulos.values():
            elemento = capitulo.buscar(id_elemento)
            if elemento is not None:
                return capitulo, elemento
        return None

    def reconstruir_referencias(self) -> None:
        """Reconstruye el índice con lo cargado; las copias de capítulos sin cargar
        se conocen por las referencias guardadas en cada `_pieza.json`."""
        self.referencias.reconstruir(self)

    @property
    def idioma_principal(self) -> str:
        return self.idiomas[0] if self.idiomas else ""

    @property
    def nombre_carpeta(self) -> str:
        return normalizar_nombre(self.nombre)
