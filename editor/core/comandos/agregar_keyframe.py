"""Poner y mover keyframes (T6.5).

`propiedad` es una propiedad animable del Elemento (espacio o audio) o, con
`indice_efecto`, un parámetro de uno de sus efectos. `f` es relativo al
inicio del Elemento.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.espacio.transform import PROPIEDADES_ANIMABLES
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import PROPIEDADES_AUDIO_ANIMABLES, Elemento
from editor.core.modelo.keyframe import Animacion, Keyframe
from editor.core.modelo.proyecto import Proyecto


def animacion_de(elemento: Elemento, propiedad: str, indice_efecto: int | None) -> Animacion:
    if indice_efecto is None:
        if propiedad not in PROPIEDADES_ANIMABLES + PROPIEDADES_AUDIO_ANIMABLES:
            raise EdicionRechazada(f"La propiedad {propiedad!r} no se puede animar.")
        return elemento.animacion
    try:
        efecto = elemento.efectos[indice_efecto]
    except IndexError:
        raise EdicionRechazada(f"No hay un efecto en la posición {indice_efecto}.") from None
    if propiedad not in efecto.parametros:
        raise EdicionRechazada(f"El efecto {efecto.tipo} no tiene el parámetro {propiedad!r}.")
    return efecto.animacion


class PonerKeyframe(EdicionCapitulo):
    descripcion = "Poner keyframe"

    def __init__(self, capitulo: int, id_elemento: str, propiedad: str, keyframe: Keyframe,
                 indice_efecto: int | None = None) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.propiedad = propiedad
        self.keyframe = keyframe
        self.indice_efecto = indice_efecto

    def clave_fusion(self) -> tuple | None:
        return ("keyframe", self.id_elemento, self.propiedad, self.indice_efecto, self.keyframe.f)

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        if self.keyframe.f >= elemento.duracion:
            raise EdicionRechazada("El keyframe cae fuera del Elemento.")
        animacion_de(elemento, self.propiedad, self.indice_efecto).pista(self.propiedad).poner(self.keyframe)
        return set()


class MoverKeyframe(EdicionCapitulo):
    descripcion = "Mover keyframe"

    def __init__(self, capitulo: int, id_elemento: str, propiedad: str, f_origen: int, f_destino: int,
                 indice_efecto: int | None = None) -> None:
        super().__init__(capitulo)
        self.id_elemento = id_elemento
        self.propiedad = propiedad
        self.f_origen = f_origen
        self.f_destino = f_destino
        self.indice_efecto = indice_efecto

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        if not 0 <= self.f_destino < elemento.duracion:
            raise EdicionRechazada("El keyframe cae fuera del Elemento.")
        pista = animacion_de(elemento, self.propiedad, self.indice_efecto).pista(self.propiedad)
        keyframe = pista.quitar(self.f_origen)
        if keyframe is None:
            raise EdicionRechazada(f"No hay keyframe en el fotograma {self.f_origen}.")
        pista.poner(Keyframe(self.f_destino, keyframe.valor, keyframe.curva, keyframe.controles))
        return set()
