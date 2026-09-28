"""Contrato de los comandos (T6.1).

Todo cambio del modelo pasa por un Comando: así deshacer y rehacer funcionan
siempre. Reglas:

- **Todo o nada**: si un comando falla a mitad, el modelo vuelve a como estaba.
- **Determinista**: los IDs nuevos se reservan la primera vez y se reutilizan
  al rehacer, para que rehacer produzca exactamente lo mismo.
- **Por ID**: la interfaz debe referirse a los Elementos por su ID; deshacer
  restaura copias, no los mismos objetos.

`EdicionCapitulo` implementa el patrón común: guarda una copia de los
Elementos involucrados antes de tocarlos y, para deshacer, restaura esas
copias. Cada comando concreto solo describe su cambio.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.errores import ErrorModelo
from editor.core.modelo.proyecto import Proyecto


class EdicionRechazada(ErrorModelo):
    """El comando no se puede aplicar (bloqueo, límite de la fuente, etc.)."""


@dataclass
class Afectados:
    """Qué tocó un comando: lo usan el historial (eventos) y las huellas."""

    capitulo: int | None = None
    agregados: set[str] = field(default_factory=set)
    quitados: set[str] = field(default_factory=set)
    cambiados: set[str] = field(default_factory=set)
    minutos: set[int] = field(default_factory=set)
    shorts: set[str] = field(default_factory=set)
    piezas: set[str] = field(default_factory=set)
    brutos: set[str] = field(default_factory=set)
    estado_capitulo: bool = False     # capas, marcadores, título…

    def invertido(self) -> "Afectados":
        """Lo mismo visto desde deshacer: lo agregado se quita y viceversa."""
        return Afectados(
            self.capitulo, set(self.quitados), set(self.agregados), set(self.cambiados), set(self.minutos),
            set(self.shorts), set(self.piezas), set(self.brutos), self.estado_capitulo,
        )

    def unir(self, otro: "Afectados") -> "Afectados":
        return Afectados(
            self.capitulo if self.capitulo is not None else otro.capitulo,
            self.agregados | otro.agregados,
            self.quitados | otro.quitados,
            self.cambiados | otro.cambiados,
            self.minutos | otro.minutos,
            self.shorts | otro.shorts,
            self.piezas | otro.piezas,
            self.brutos | otro.brutos,
            self.estado_capitulo or otro.estado_capitulo,
        )


class Comando(ABC):
    descripcion: str = "Edición"

    @abstractmethod
    def ejecutar(self, proyecto: Proyecto) -> None:
        """Aplica el cambio. Si falla, deja el modelo intacto y lanza el error."""

    @abstractmethod
    def deshacer(self, proyecto: Proyecto) -> None: ...

    @abstractmethod
    def afectados(self) -> list[Afectados]:
        """Uno por capítulo tocado (o uno sin capítulo para el Taller)."""

    def fusionar(self, siguiente: "Comando") -> bool:
        """Absorbe `siguiente` si es la continuación del mismo gesto (arrastres). Por defecto, no."""
        return False


# --- Utilidades comunes -------------------------------------------------------------

def minutos_de(elemento: Elemento) -> set[int]:
    return set(elemento.minutos_cruzados)


def sincronizar_con_fuente(proyecto: Proyecto, elemento: Elemento) -> None:
    """Alinea los datos de la fuente con el horneado vigente de su Pieza.

    El horneado es estado automático: una copia restaurada al deshacer no debe
    volver a una versión cuyo archivo ya fue reemplazado.
    """
    from editor.core.modelo.capa import TipoCapa
    from editor.core.modelo.elemento import ReferenciaFuente, TipoFuente

    if elemento.fuente.tipo is not TipoFuente.PIEZA:
        return
    pieza = proyecto.taller.piezas.get(elemento.fuente.ref)
    if pieza is None or pieza.horneado is None or pieza.horneado.version == elemento.fuente.version:
        return
    horneado = pieza.horneado
    elemento.fuente = ReferenciaFuente(TipoFuente.PIEZA, pieza.id, horneado.version)
    elemento.tiempo.fuente_duracion = horneado.fotogramas
    elemento.tiene_audio = horneado.tiene_audio
    if elemento.capa.tipo is not TipoCapa.AUDIO:
        elemento.extension = horneado.extension
        elemento.ancho, elemento.alto = horneado.ancho, horneado.alto
        elemento.tiene_alfa = horneado.tiene_alfa


def insertar_directo(capitulo: Capitulo, elemento: Elemento) -> None:
    """Inserta sin validar: solo para restaurar un estado que ya fue válido."""
    capitulo.contenedor_de(elemento).elementos[elemento.id] = elemento


def quitar_si_esta(capitulo: Capitulo, id_elemento: str) -> Elemento | None:
    elemento = capitulo.buscar(id_elemento)
    if elemento is None:
        return None
    capitulo.contenedor_de(elemento).elementos.pop(id_elemento, None)
    return elemento


class ReservaIds:
    """IDs nuevos estables entre ejecuciones del mismo comando (rehacer = mismo resultado)."""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._indice = 0

    def reiniciar(self) -> None:
        self._indice = 0

    def nuevo(self, proyecto: Proyecto) -> str:
        if self._indice < len(self._ids):
            identificador = self._ids[self._indice]
            proyecto.ids.registrar(identificador)
        else:
            identificador = proyecto.nuevo_id()
            self._ids.append(identificador)
        self._indice += 1
        return identificador


class EdicionCapitulo(Comando):
    """Edición de Elementos de un capítulo con deshacer por instantáneas."""

    def __init__(self, capitulo: int) -> None:
        self.capitulo = capitulo
        self.ids = ReservaIds()
        # IDs que el comando crea sin pasar por `ids` (p. ej. el Elemento que agrega).
        self.ids_propios: set[str] = set()
        self._antes: dict[str, Elemento] = {}
        self._despues: set[str] = set()
        self._afectados = Afectados(capitulo)

    # --- A implementar -------------------------------------------------------------

    @abstractmethod
    def involucrados(self, capitulo: Capitulo) -> set[str]:
        """IDs de los Elementos que el comando puede modificar o quitar."""

    @abstractmethod
    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        """Hace el cambio y devuelve los IDs de los Elementos que creó."""

    # --- Ayudas para las subclases ---------------------------------------------------

    def obtener(self, capitulo: Capitulo, id_elemento: str, editable: bool = True) -> Elemento:
        elemento = capitulo.obtener(id_elemento)
        if editable and not capitulo.editable(elemento):
            raise EdicionRechazada(f"El Elemento {id_elemento} o su capa están bloqueados.")
        return elemento

    @staticmethod
    def retirar(capitulo: Capitulo, elementos: list[Elemento]) -> None:
        for elemento in elementos:
            capitulo.contenedor_de(elemento).elementos.pop(elemento.id, None)

    @staticmethod
    def colocar(capitulo: Capitulo, elementos: list[Elemento]) -> None:
        """Agrega validando reglas (solapes, minuto) en orden de inicio."""
        for elemento in sorted(elementos, key=lambda e: e.inicio):
            if elemento.excede_fuente:
                raise EdicionRechazada(f"El Elemento {elemento.id} pide más material del que tiene su fuente.")
            capitulo.agregar(elemento)

    # --- Mecánica ------------------------------------------------------------------------

    def ejecutar(self, proyecto: Proyecto) -> None:
        capitulo = proyecto.capitulo(self.capitulo)
        self.ids.reiniciar()
        ids_previos = {i for i in self.involucrados(capitulo) if capitulo.buscar(i) is not None}
        self._antes = {i: copy.deepcopy(capitulo.obtener(i)) for i in ids_previos}
        try:
            creados = self.aplicar(proyecto, capitulo)
        except Exception:
            self._restaurar(proyecto, capitulo, ids_previos | set(self.ids._ids) | self.ids_propios)
            raise
        despues = {i for i in ids_previos | creados if capitulo.buscar(i) is not None}
        self._despues = despues
        self._afectados = self._calcular_afectados(capitulo, ids_previos, despues)
        self._registrar(proyecto, capitulo, ids_previos | despues)

    def deshacer(self, proyecto: Proyecto) -> None:
        capitulo = proyecto.capitulo(self.capitulo)
        self._restaurar(proyecto, capitulo, self._despues | set(self._antes))

    def _restaurar(self, proyecto: Proyecto, capitulo: Capitulo, ids: set[str]) -> None:
        for identificador in ids:
            quitar_si_esta(capitulo, identificador)
        for elemento in self._antes.values():
            restaurado = copy.deepcopy(elemento)
            sincronizar_con_fuente(proyecto, restaurado)
            insertar_directo(capitulo, restaurado)
        self._registrar(proyecto, capitulo, ids)

    @staticmethod
    def _registrar(proyecto: Proyecto, capitulo: Capitulo, ids: set[str]) -> None:
        for identificador in ids:
            elemento = capitulo.buscar(identificador)
            if elemento is None:
                proyecto.referencias.olvidar(identificador)
            else:
                proyecto.referencias.registrar(elemento, capitulo.numero)

    def _calcular_afectados(self, capitulo: Capitulo, antes: set[str], despues: set[str]) -> Afectados:
        minutos: set[int] = set()
        for elemento in self._antes.values():
            minutos |= minutos_de(elemento)
        for identificador in despues:
            minutos |= minutos_de(capitulo.obtener(identificador))
        return Afectados(
            capitulo=self.capitulo,
            agregados=despues - antes,
            quitados=antes - despues,
            cambiados=antes & despues,
            minutos=minutos,
        )

    def afectados(self) -> list[Afectados]:
        return [self._afectados]

    # --- Fusión de gestos continuos ------------------------------------------------------

    def clave_fusion(self) -> tuple | None:
        """Comandos con parámetros **absolutos** del mismo gesto devuelven la misma clave."""
        return None

    def fusionar(self, siguiente: Comando) -> bool:
        clave = self.clave_fusion()
        if clave is None or type(siguiente) is not type(self):
            return False
        assert isinstance(siguiente, EdicionCapitulo)
        if siguiente.clave_fusion() != clave:
            return False
        # Conserva el estado previo del primer paso y adopta los parámetros finales:
        # rehacer desde ese estado con valores absolutos da el resultado final.
        antes = self._antes
        afectados = self._afectados
        self.__dict__.update({k: v for k, v in siguiente.__dict__.items() if k != "_antes"})
        self._antes = antes
        self._afectados = afectados.unir(siguiente._afectados)
        return True
