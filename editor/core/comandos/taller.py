"""Comandos del Taller: Brutos y Piezas (T6.8).

Importar un archivo (copiarlo y analizarlo) es un servicio (E9); el comando
solo registra el Bruto resultante en el modelo. Cambiar la receta de una Pieza
la marca como no horneada; hornear también es un servicio (E9).
"""

from __future__ import annotations

import copy
from dataclasses import replace
from fractions import Fraction

from editor.core.comandos.comando import Afectados, Comando, EdicionRechazada
from editor.core.espacio.transform import Transform
from editor.core.modelo.bruto import Bruto
from editor.core.modelo.efecto import Efecto
from editor.core.modelo.pieza import AudioConformado, MetodoConversionFps, Pieza, TramoFuente
from editor.core.modelo.proyecto import Proyecto
from editor.core.tiempo.nomenclatura import es_nombre_valido


class _EdicionTaller(Comando):
    """Guarda una copia del Bruto o la Pieza antes de cambiarlo; deshacer la restaura."""

    def __init__(self) -> None:
        self._brutos_antes: dict[str, Bruto | None] = {}
        self._piezas_antes: dict[str, Pieza | None] = {}
        self._afectados = Afectados()

    def _guardar_bruto(self, proyecto: Proyecto, id_bruto: str) -> None:
        actual = proyecto.taller.brutos.get(id_bruto)
        self._brutos_antes.setdefault(id_bruto, copy.deepcopy(actual))

    def _guardar_pieza(self, proyecto: Proyecto, id_pieza: str) -> None:
        actual = proyecto.taller.piezas.get(id_pieza)
        self._piezas_antes.setdefault(id_pieza, copy.deepcopy(actual))

    def deshacer(self, proyecto: Proyecto) -> None:
        for identificador, bruto in self._brutos_antes.items():
            if bruto is None:
                proyecto.taller.brutos.pop(identificador, None)
            else:
                proyecto.taller.brutos[identificador] = copy.deepcopy(bruto)
        for identificador, pieza in self._piezas_antes.items():
            if pieza is None:
                proyecto.taller.piezas.pop(identificador, None)
            else:
                restaurada = copy.deepcopy(pieza)
                proyecto.taller.piezas[identificador] = restaurada
                proyecto.referencias.registrar_pieza(identificador, restaurada.ids_brutos())

    def _reiniciar(self) -> None:
        self._brutos_antes = {}
        self._piezas_antes = {}

    def afectados(self) -> list[Afectados]:
        return [self._afectados]


class AgregarBruto(_EdicionTaller):
    descripcion = "Importar"

    def __init__(self, bruto: Bruto) -> None:
        super().__init__()
        self.bruto = copy.deepcopy(bruto)

    def ejecutar(self, proyecto: Proyecto) -> None:
        self._reiniciar()
        self._guardar_bruto(proyecto, self.bruto.id)
        proyecto.ids.registrar(self.bruto.id)
        proyecto.taller.agregar_bruto(copy.deepcopy(self.bruto))
        self._afectados = Afectados(brutos={self.bruto.id})


class QuitarBruto(_EdicionTaller):
    descripcion = "Quitar Bruto"

    def __init__(self, id_bruto: str) -> None:
        super().__init__()
        self.id_bruto = id_bruto

    def ejecutar(self, proyecto: Proyecto) -> None:
        self._reiniciar()
        _, dependientes = proyecto.referencias.dependientes_de_bruto(self.id_bruto)
        if dependientes:
            raise EdicionRechazada(f"El Bruto se usa en {len(dependientes)} Elementos; quítelos primero.")
        self._guardar_bruto(proyecto, self.id_bruto)
        proyecto.taller.quitar_bruto(self.id_bruto)
        self._afectados = Afectados(brutos={self.id_bruto})


class InterpretarFps(_EdicionTaller):
    """Fija el fps con el que se interpreta un Bruto (PROJECT.md, 6.7). None = volver al medido."""

    descripcion = "Interpretar fps"

    def __init__(self, id_bruto: str, fps: Fraction | None) -> None:
        super().__init__()
        if fps is not None and fps <= 0:
            raise ValueError("El fps debe ser positivo.")
        self.id_bruto = id_bruto
        self.fps = fps

    def ejecutar(self, proyecto: Proyecto) -> None:
        self._reiniciar()
        self._guardar_bruto(proyecto, self.id_bruto)
        bruto = proyecto.taller.bruto(self.id_bruto)
        bruto.fps_interpretado = self.fps
        piezas = proyecto.taller.piezas_de_bruto(self.id_bruto)
        for pieza in piezas:
            self._guardar_pieza(proyecto, pieza.id)
            pieza.receta_modificada = True
        self._afectados = Afectados(brutos={self.id_bruto}, piezas={p.id for p in piezas})


class AgregarPieza(_EdicionTaller):
    descripcion = "Crear Pieza"

    def __init__(self, pieza: Pieza) -> None:
        super().__init__()
        self.pieza = copy.deepcopy(pieza)

    def ejecutar(self, proyecto: Proyecto) -> None:
        self._reiniciar()
        self._guardar_pieza(proyecto, self.pieza.id)
        proyecto.ids.registrar(self.pieza.id)
        nueva = copy.deepcopy(self.pieza)
        proyecto.taller.agregar_pieza(nueva)
        proyecto.referencias.registrar_pieza(nueva.id, nueva.ids_brutos())
        self._afectados = Afectados(piezas={self.pieza.id})


class QuitarPieza(_EdicionTaller):
    """Quita la Pieza del Taller. Sus copias en los minutos siguen funcionando (son autosuficientes)."""

    descripcion = "Quitar Pieza"

    def __init__(self, id_pieza: str) -> None:
        super().__init__()
        self.id_pieza = id_pieza

    def ejecutar(self, proyecto: Proyecto) -> None:
        self._reiniciar()
        self._guardar_pieza(proyecto, self.id_pieza)
        proyecto.taller.quitar_pieza(self.id_pieza)
        proyecto.referencias.registrar_pieza(self.id_pieza, set())
        self._afectados = Afectados(piezas={self.id_pieza})


class CambiarRecetaPieza(_EdicionTaller):
    """Cambia tramos, método de fps, audio conformado, transformación, efectos o nombre."""

    descripcion = "Cambiar Pieza"

    def __init__(
        self,
        id_pieza: str,
        tramos: list[TramoFuente] | None = None,
        metodo_fps: MetodoConversionFps | None = None,
        audio_conformado: AudioConformado | None = None,
        espacio: Transform | None = None,
        efectos: list[Efecto] | None = None,
        nombre: str | None = None,
    ) -> None:
        super().__init__()
        if nombre is not None and not es_nombre_valido(nombre):
            raise ValueError("Nombre descriptivo inválido: minúsculas, números y guiones.")
        self.id_pieza = id_pieza
        self.cambios = {
            clave: copy.deepcopy(valor)
            for clave, valor in {
                "tramos": tramos, "metodo_fps": metodo_fps, "audio_conformado": audio_conformado,
                "espacio": espacio, "efectos": efectos, "nombre": nombre,
            }.items()
            if valor is not None
        }

    def ejecutar(self, proyecto: Proyecto) -> None:
        self._reiniciar()
        pieza = proyecto.taller.pieza(self.id_pieza)
        faltantes = {t.id_bruto for t in self.cambios.get("tramos", [])} - proyecto.taller.brutos.keys()
        if faltantes:
            raise EdicionRechazada(f"Tramos con Brutos inexistentes: {', '.join(sorted(faltantes))}")
        self._guardar_pieza(proyecto, self.id_pieza)
        nueva = replace(pieza, **copy.deepcopy(self.cambios))
        if set(self.cambios) - {"nombre"}:
            nueva.receta_modificada = True
        proyecto.taller.piezas[self.id_pieza] = nueva
        proyecto.referencias.registrar_pieza(self.id_pieza, nueva.ids_brutos())
        self._afectados = Afectados(piezas={self.id_pieza})
