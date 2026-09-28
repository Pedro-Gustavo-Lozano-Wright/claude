"""Ripple: recortar un borde y correr lo que sigue para no dejar hueco (T6.6).

Alcance (PROJECT.md, 6.5):
- MINUTO (por defecto): se corre lo que empieza en el mismo minuto.
- CAPITULO: se corre todo lo posterior del capítulo (renombres en cascada al
  guardar; la interfaz debe confirmarlo antes).

Se corren todas las capas de los minutos (no Global), como en los editores
profesionales, para mantener la sincronía entre video, audio y textos.
"""

from __future__ import annotations

from editor.core.comandos.comando import EdicionCapitulo, EdicionRechazada
from editor.core.comandos.operaciones import Alcance, a_desplazar, desplazar, fijar_keyframe_en
from editor.core.comandos.recortar_elemento import FIN, INICIO
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.proyecto import Proyecto


class RippleRecorte(EdicionCapitulo):
    descripcion = "Ripple"

    def __init__(self, capitulo: int, id_elemento: str, lado: str, delta: int, alcance: Alcance = Alcance.MINUTO) -> None:
        """`delta` en fotogramas: positivo acorta desde ese lado; negativo lo alarga."""
        super().__init__(capitulo)
        if lado not in (INICIO, FIN):
            raise ValueError(f"Lado desconocido: {lado!r}")
        self.id_elemento = id_elemento
        self.lado = lado
        self.delta = delta
        self.alcance = alcance

    def _siguientes(self, capitulo: Capitulo) -> list:
        elemento = capitulo.obtener(self.id_elemento)
        return a_desplazar(capitulo, elemento.fin, self.alcance, elemento.minuto_inicio, ignorar={elemento.id})

    def involucrados(self, capitulo: Capitulo) -> set[str]:
        return {self.id_elemento} | {e.id for e in self._siguientes(capitulo)}

    def aplicar(self, proyecto: Proyecto, capitulo: Capitulo) -> set[str]:
        elemento = self.obtener(capitulo, self.id_elemento)
        if elemento.en_global:
            raise EdicionRechazada("El ripple se aplica a Elementos de los minutos.")
        siguientes = self._siguientes(capitulo)
        for otro in siguientes:
            self.obtener(capitulo, otro.id)
        if self.delta >= elemento.duracion:
            raise EdicionRechazada("El ripple dejaría el Elemento sin duración.")
        self.retirar(capitulo, [elemento] + siguientes)

        tiempo = elemento.tiempo
        if self.lado == INICIO:
            # El inicio en pantalla queda fijo; se consume (o recupera) material de la fuente.
            if not tiempo.congelado:
                avance = (elemento.avance_fuente(self.delta) if self.delta > 0 and elemento.con_rampa
                          else self.delta * abs(tiempo.velocidad))
                nueva_entrada = tiempo.fuente_entrada + round(avance)
                if nueva_entrada < 0:
                    raise EdicionRechazada("No hay más material de la fuente antes de la entrada.")
                tiempo.fuente_entrada = nueva_entrada
            if self.delta > 0:
                fijar_keyframe_en(elemento, self.delta)
            elemento.animacion = elemento.animacion.desplazada(-self.delta)
            for efecto in elemento.efectos:
                efecto.animacion = efecto.animacion.desplazada(-self.delta)
        elif self.delta > 0:
            fijar_keyframe_en(elemento, elemento.duracion - self.delta)
        tiempo.duracion -= self.delta

        desplazar(siguientes, -self.delta)
        self.colocar(capitulo, [elemento] + siguientes)
        return set()

