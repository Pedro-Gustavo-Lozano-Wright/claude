"""Separar el audio de un Elemento V en un Elemento A independiente (T6.4).

El Elemento A referencia la misma Pieza; al guardar, su archivo WAV se extrae
de la Pieza (materialización pendiente, E9). El Elemento V queda silenciado.
"""

from __future__ import annotations

import copy

from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.espacio.transform import Transform
from editor.core.modelo.capa import Capa, TipoCapa
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import PROPIEDADES_AUDIO_ANIMABLES
from editor.core.modelo.keyframe import Animacion
from editor.core.modelo.proyecto import Proyecto


class SepararAudio(EdicionCapitulo):
    descripcion = "Separar audio"

    def __init__(self, capitulo: int, id_elemento: str, capa_audio: Capa) -> None:
        super().__init__(capitulo)
        if capa_audio.tipo is not TipoCapa.AUDIO:
            raise ValueError("El audio separado va en una capa A.")
        self.id_elemento = id_elemento
        self.capa_audio = capa_audio

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        video = self.obtener(capitulo, self.id_elemento)
        if video.capa.tipo is not TipoCapa.VIDEO or not video.tiene_audio:
            raise EdicionRechazada("Solo se separa el audio de un Elemento de video que tenga audio.")
        if video.audio.silenciado:
            raise EdicionRechazada("El audio de este Elemento ya está silenciado o separado.")
        audio = copy.deepcopy(video)
        audio.id = self.ids.nuevo(proyecto)
        audio.capa = self.capa_audio
        audio.extension = "wav"
        audio.archivo = None
        audio.ancho = audio.alto = 0
        audio.tiene_alfa = False
        audio.espacio = Transform()
        audio.efectos = []
        audio.transicion_entrada = None
        audio.animacion = Animacion({
            clave: pista for clave, pista in audio.animacion.pistas.items() if clave in PROPIEDADES_AUDIO_ANIMABLES
        })
        video.audio.silenciado = True
        self.colocar(capitulo, [audio])
        return {audio.id}
