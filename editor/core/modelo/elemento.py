"""El Elemento: bloque fundamental del editor (PROJECT.md, sección 8).

Una ventana de tiempo sobre un archivo, colocada en el lienzo y en la
timeline, cuyas propiedades son parámetros animables.

El Elemento sabe responder qué aporta en un fotograma (activo o no, qué
fotograma de su fuente, con qué transformación y volumen). La obtención de la
imagen y la mezcla son del motor (E7).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from enum import Enum
from pathlib import Path

from editor.core.espacio.transform import PROPIEDADES_ANIMABLES, Transform
from editor.core.estandar import ASAS_FOTOGRAMAS, FOTOGRAMAS_POR_CAPITULO
from editor.core.modelo.capa import Capa, TipoCapa
from editor.core.modelo.efecto import Efecto
from editor.core.modelo.keyframe import Animacion
from editor.core.modelo.texto import ContenidoTexto
from editor.core.modelo.transicion import Transicion
from editor.core.tiempo import granularidad
from editor.core.tiempo.granularidad import Duracion, Instante
from editor.core.tiempo.nomenclatura import NombreElemento

PROPIEDADES_AUDIO_ANIMABLES = ("volumen", "paneo")
# Rampas de velocidad (E19): keyframes de "velocidad" (siempre positiva; la reversa no se anima).
PROPIEDADES_TIEMPO_ANIMABLES = ("velocidad",)
VELOCIDAD_MINIMA, VELOCIDAD_MAXIMA = 0.05, 8.0


@lru_cache(maxsize=256)
def _avance_acumulado(keyframes: tuple, base: float, fotogramas: int) -> tuple[float, ...]:
    """Fotogramas de fuente avanzados al comienzo de cada fotograma local 0…fotogramas (regla del trapecio)."""
    from editor.core.modelo.keyframe import PistaKeyframes

    pista = PistaKeyframes(list(keyframes))
    valores = [max(VELOCIDAD_MINIMA, pista.valor_en(k, base)) for k in range(fotogramas + 1)]
    acumulado = [0.0]
    for k in range(fotogramas):
        acumulado.append(acumulado[-1] + (valores[k] + valores[k + 1]) / 2)
    return tuple(acumulado)


class TipoFuente(Enum):
    PIEZA = "pieza"
    BRUTO = "bruto"   # solo para imágenes y audio colocados sin pasar por una Pieza de video
    TEXTO = "texto"


@dataclass(frozen=True)
class ReferenciaFuente:
    tipo: TipoFuente
    ref: str = ""       # ID de la Pieza o del Bruto; vacío para texto
    version: int = 0    # versión de la Pieza con la que se materializó la copia


@dataclass
class TiempoElemento:
    inicio: int                      # fotograma del capítulo
    duracion: int                    # fotogramas
    # Fotograma de la fuente (24 fps) donde empieza. Para una Pieza vale sus asas de
    # inicio (normalmente 24); para imágenes, textos y audio colocado directo, 0.
    fuente_entrada: int = ASAS_FOTOGRAMAS
    velocidad: float = 1.0           # negativa = reversa
    # Fotogramas que tiene la fuente, asas incluidas; 0 = ilimitada (imagen fija, texto).
    fuente_duracion: int = 0
    # Congelar fotograma: muestra siempre `fuente_entrada` durante toda la duración.
    congelado: bool = False

    def __post_init__(self) -> None:
        if self.inicio < 0:
            raise ValueError("El inicio no puede ser negativo.")
        if self.duracion <= 0:
            raise ValueError("La duración debe ser positiva.")
        if self.fuente_entrada < 0:
            raise ValueError("La entrada de la fuente no puede ser negativa.")
        if self.velocidad == 0:
            raise ValueError("La velocidad no puede ser cero.")

    @property
    def fin(self) -> int:
        """Primer fotograma después del Elemento (exclusivo)."""
        return self.inicio + self.duracion

    @property
    def fotogramas_fuente_usados(self) -> int:
        """Cuántos fotogramas de la fuente consume el Elemento."""
        if self.congelado:
            return 1
        return max(1, math.ceil(self.duracion * abs(self.velocidad)))

    @property
    def excede_fuente(self) -> bool:
        """True si trim, slip o velocidad piden más material del que tiene la fuente."""
        if self.fuente_duracion <= 0:
            return False
        return self.fuente_entrada + self.fotogramas_fuente_usados > self.fuente_duracion

    @property
    def margen_fuente(self) -> tuple[int, int]:
        """Fotogramas de fuente libres antes y después del tramo usado (para trim y slip)."""
        if self.fuente_duracion <= 0:
            return (self.fuente_entrada, 10**9)
        despues = self.fuente_duracion - self.fuente_entrada - self.fotogramas_fuente_usados
        return (self.fuente_entrada, max(0, despues))


@dataclass
class AudioElemento:
    volumen: float = 1.0          # 0.0 – 2.0
    paneo: float = 0.0            # -1.0 izquierda … 1.0 derecha
    silenciado: bool = False
    fundido_entrada: int = 0      # fotogramas
    fundido_salida: int = 0


@dataclass
class EstadoElemento:
    activo: bool = True
    bloqueado: bool = False


@dataclass
class Elemento:
    id: str
    nombre: str
    capa: Capa
    tiempo: TiempoElemento
    fuente: ReferenciaFuente
    extension: str = "json"
    ancho: int = 0                 # tamaño natural del archivo (0 para audio)
    alto: int = 0
    tiene_alfa: bool = False
    tiene_audio: bool = False
    espacio: Transform = field(default_factory=Transform)
    animacion: Animacion = field(default_factory=Animacion)
    efectos: list[Efecto] = field(default_factory=list)
    transicion_entrada: Transicion | None = None
    audio: AudioElemento = field(default_factory=AudioElemento)
    estado: EstadoElemento = field(default_factory=EstadoElemento)
    texto: ContenidoTexto | None = None
    en_global: bool = False
    # Ruta del archivo materializado en disco; la asigna proyecto_fs (E5).
    archivo: Path | None = None

    def __post_init__(self) -> None:
        if self.capa.tipo is TipoCapa.TEXTO:
            if self.texto is None:
                self.texto = ContenidoTexto()
            self.fuente = ReferenciaFuente(TipoFuente.TEXTO)
            self.extension = "json"

    # --- Tiempo ----------------------------------------------------------------

    @property
    def inicio(self) -> int:
        return self.tiempo.inicio

    @property
    def fin(self) -> int:
        return self.tiempo.fin

    @property
    def duracion(self) -> int:
        return self.tiempo.duracion

    @property
    def con_rampa(self) -> bool:
        return self.animacion.tiene("velocidad") and not self.tiempo.congelado and self.tiempo.velocidad > 0

    def avance_fuente(self, local: float) -> float:
        """Fotogramas de fuente recorridos desde el inicio del Elemento hasta `local` (rampas incluidas)."""
        if not self.con_rampa:
            return max(0.0, local) * abs(self.tiempo.velocidad)
        acumulado = _avance_acumulado(tuple(self.animacion.pista("velocidad").keyframes),
                                      float(self.tiempo.velocidad), self.duracion)
        if local <= 0:
            return 0.0
        k = min(int(local), self.duracion - 1)
        return acumulado[k] + (acumulado[k + 1] - acumulado[k]) * (min(local, self.duracion) - k)

    @property
    def fuente_usada(self) -> int:
        """Fotogramas de fuente que consume el Elemento (con rampa, la integral de la velocidad)."""
        if not self.con_rampa:
            return self.tiempo.fotogramas_fuente_usados
        return max(1, math.ceil(self.avance_fuente(self.duracion) - 1e-9))

    @property
    def excede_fuente(self) -> bool:
        if not self.con_rampa:
            return self.tiempo.excede_fuente
        return self.tiempo.fuente_duracion > 0 and self.tiempo.fuente_entrada + self.fuente_usada > self.tiempo.fuente_duracion

    @property
    def margen_fuente(self) -> tuple[int, int]:
        if not self.con_rampa or self.tiempo.fuente_duracion <= 0:
            return self.tiempo.margen_fuente
        despues = self.tiempo.fuente_duracion - self.tiempo.fuente_entrada - self.fuente_usada
        return (self.tiempo.fuente_entrada, max(0, despues))

    @property
    def minuto_inicio(self) -> int:
        return granularidad.minuto_de(self.inicio)

    @property
    def minutos_cruzados(self) -> range:
        return granularidad.minutos_cruzados(self.inicio, self.fin)

    @property
    def desborda(self) -> bool:
        """True si termina en un minuto posterior al de su inicio."""
        return granularidad.minuto_de(self.fin - 1) != self.minuto_inicio

    @property
    def excede_capitulo(self) -> bool:
        """True si una parte queda después de 24:00 (regla del marco temporal)."""
        return self.fin > FOTOGRAMAS_POR_CAPITULO

    def contiene(self, f: int) -> bool:
        return self.inicio <= f < self.fin

    def activo_en(self, f: int) -> bool:
        return self.estado.activo and self.contiene(f) and granularidad.dentro_del_capitulo(f)

    def local(self, f: float) -> float:
        """Fotograma relativo al inicio del Elemento (el que usan los keyframes)."""
        return f - self.inicio

    def fotograma_fuente(self, f: int) -> int:
        """Fotograma de la fuente (Pieza a 24 fps) que se ve en el fotograma f del capítulo."""
        if self.tiempo.congelado:
            return self.tiempo.fuente_entrada
        desplazamiento = math.floor(self.avance_fuente(f - self.inicio) + 1e-9)
        if self.tiempo.velocidad > 0:
            return self.tiempo.fuente_entrada + desplazamiento
        ultimo = self.tiempo.fuente_entrada + self.tiempo.fotogramas_fuente_usados - 1
        return max(self.tiempo.fuente_entrada, ultimo - desplazamiento)

    # --- Espacio y audio animados ----------------------------------------------

    def transform_en(self, f: float) -> Transform:
        bases = {propiedad: float(getattr(self.espacio, propiedad)) for propiedad in PROPIEDADES_ANIMABLES}
        return self.espacio.con_valores(self.animacion.valores(self.local(f), bases))

    def volumen_en(self, f: float) -> float:
        if self.audio.silenciado:
            return 0.0
        volumen = self.animacion.valor("volumen", self.local(f), self.audio.volumen)
        return volumen * self._fundido(f)

    def paneo_en(self, f: float) -> float:
        return self.animacion.valor("paneo", self.local(f), self.audio.paneo)

    def _fundido(self, f: float) -> float:
        local = self.local(f)
        factor = 1.0
        if self.audio.fundido_entrada > 0 and local < self.audio.fundido_entrada:
            factor = min(factor, max(0.0, local / self.audio.fundido_entrada))
        restante = self.duracion - local
        if self.audio.fundido_salida > 0 and restante < self.audio.fundido_salida:
            factor = min(factor, max(0.0, restante / self.audio.fundido_salida))
        return factor

    # --- Naturaleza ------------------------------------------------------------

    @property
    def es_visual(self) -> bool:
        return self.capa.es_visual

    @property
    def es_texto(self) -> bool:
        return self.capa.tipo is TipoCapa.TEXTO

    @property
    def suena(self) -> bool:
        """Aporta audio a la mezcla: capas A, o V con audio y sin silenciar (PROJECT.md, 8.4)."""
        if self.audio.silenciado or self.es_texto:
            return False
        return self.capa.tipo is TipoCapa.AUDIO or self.tiene_audio

    @property
    def orden_apilado(self) -> int | None:
        return self.capa.orden_apilado(self.en_global)

    # --- Nombre en disco -------------------------------------------------------

    def nombre_archivo(self) -> NombreElemento:
        return NombreElemento(
            inicio=Instante(self.inicio),
            duracion=Duracion(self.duracion),
            capa=self.capa.codigo,
            nombre=self.nombre,
            id=self.id,
            extension=self.extension,
        )

    def __repr__(self) -> str:
        return f"Elemento({self.id} {self.capa} {Instante(self.inicio)} +{self.duracion} '{self.nombre}')"
