"""Audio avanzado desde la interfaz (E20): ducking, sonoridad y reducción de ruido."""

from __future__ import annotations

import copy
from typing import Callable

from editor.app.estado import Sesion
from editor.core.comandos import PonerKeyframe
from editor.core.comandos.compuesto import ComandoCompuesto
from editor.core.estandar import FOTOGRAMAS_POR_MINUTO, FPS
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.keyframe import Keyframe
from editor.core.motor.mezclador_audio import Mezclador
from editor.core.servicios import analisis, audio_procesado
from editor.core.tareas.cola import BANCO_VISIBLE, Tarea
from editor.core.tiempo.nomenclatura import CARPETA_CACHE

ATAQUE = 6      # fotogramas para bajar antes de la voz
LIBERACION = 12  # fotogramas para volver después


def ducking(sesion: Sesion, id_musica: str, reduccion_db: float = 12.0) -> None:
    """Baja la música mientras hay voz, con keyframes de volumen (se deshace en un paso).

    Voz = los audios de capas con idioma (diálogo); si ninguna capa tiene idioma, todos
    los demás audios de los minutos. Se analiza lo que suenan juntos en el tramo de la música.
    """
    capitulo = sesion.capitulo
    musica = capitulo.buscar(id_musica)
    if musica is None or not musica.suena:
        sesion.avisar("Elija el audio de música.")
        return
    otros = [e for e in capitulo.todos_los_elementos()
             if e.suena and e.id != id_musica and e.inicio < musica.fin and musica.inicio < e.fin]
    con_idioma = [e for e in otros if capitulo.estado_capa(e).idioma]
    voces = con_idioma or [e for e in otros if not e.en_global]
    if not voces:
        sesion.avisar("No hay voces en el tramo de la música.")
        return
    solo = Capitulo(numero=capitulo.numero)
    for voz in voces:
        duplicado = copy.deepcopy(voz)
        solo.contenedor_de(duplicado).elementos[duplicado.id] = duplicado
    mezclador = Mezclador(sesion.vista_previa.resolutor)
    inicio, fin = musica.inicio, musica.fin
    base = musica.audio.volumen
    numero = sesion.estado.capitulo

    def trabajo(contexto):
        contexto.progreso(0.2, "Buscando la voz")
        return analisis.tramos_activos(analisis.actividad(mezclador.mezclar(solo, inicio, fin)))

    def terminar(tramos, error) -> None:
        if error is not None:
            sesion.avisar(f"No se pudo analizar la voz: {error}")
            return
        actual = sesion.capitulo.buscar(id_musica)
        if actual is None or not tramos:
            sesion.avisar("No se detectó voz en el tramo de la música.")
            return
        bajo = base * 10 ** (-reduccion_db / 20)
        # Frases separadas por menos que bajar + subir se tratan como una (sin rebotes de volumen).
        unidos: list[list[int]] = []
        for desde_s, hasta_s in tramos:
            a, b = round(desde_s * FPS), round(hasta_s * FPS)
            if unidos and a - unidos[-1][1] <= ATAQUE + LIBERACION:
                unidos[-1][1] = b
            else:
                unidos.append([a, b])
        puntos: dict[int, float] = {0: base}
        for a, b in unidos:
            puntos[max(0, a - ATAQUE)] = base if a - ATAQUE > 0 else bajo
            puntos[a] = bajo
            puntos[b] = bajo
            puntos[b + LIBERACION] = base
        ultimo = actual.duracion - 1
        comandos = [PonerKeyframe(numero, id_musica, "volumen", Keyframe(f, v))
                    for f, v in sorted(puntos.items()) if 0 <= f <= ultimo]
        if sesion.ejecutar(lambda: ComandoCompuesto("Bajar música con la voz", comandos)):
            sesion.avisar(f"Música bajada {reduccion_db:.0f} dB en {len(tramos)} tramos de voz.")

    sesion.tarea(Tarea("analisis", "Buscar voz para bajar la música", trabajo, prioridad=BANCO_VISIBLE,
                       clave=f"ducking-{id_musica}"), terminar)


def medir_sonoridad(sesion: Sesion, desde: int | None, hasta: int | None,
                    al_terminar: Callable[[float, float], None]) -> None:
    """LUFS integrados y pico del rango de minutos (None = capítulo) en el idioma de escucha."""
    primero = 0 if desde is None else desde
    ultimo = len(sesion.capitulo.minutos) - 1 if desde is None else (hasta if hasta is not None else desde)
    inicio, fin = primero * FOTOGRAMAS_POR_MINUTO, (ultimo + 1) * FOTOGRAMAS_POR_MINUTO
    capitulo = sesion.capitulo.instantanea(inicio, fin)
    mezclador = Mezclador(sesion.vista_previa.resolutor)
    idioma = sesion.estado.idioma_escucha

    def trabajo(contexto):
        contexto.progreso(0.1, "Mezclando para medir")
        return analisis.sonoridad(mezclador.mezclar(capitulo, inicio, fin, idioma))

    sesion.tarea(Tarea("analisis", "Medir sonoridad", trabajo, prioridad=BANCO_VISIBLE, clave="sonoridad"),
                 lambda resultado, error: sesion.avisar(f"No se pudo medir: {error}") if error
                 else al_terminar(*resultado))


def reducir_ruido(sesion: Sesion, id_bruto: str) -> None:
    """Crea un Bruto nuevo con el ruido reducido (el original no cambia)."""
    from editor.app.controladores import medios

    bruto = sesion.proyecto.taller.bruto(id_bruto)
    if bruto.archivo is None or not (bruto.tiene_audio or bruto.tipo.value == "audio"):
        sesion.avisar("El Bruto no tiene audio.")
        return
    assert sesion.proyecto.raiz is not None
    entrada = bruto.archivo
    salida = sesion.proyecto.raiz / CARPETA_CACHE / "procesado" / f"{bruto.nombre}-limpio.wav"

    def terminar(ruta, error) -> None:
        if error is not None:
            sesion.avisar(f"No se pudo reducir el ruido: {error}")
            return
        medios.importar(sesion, [ruta])
        sesion.avisar(f"Importando {ruta.name} (ruido reducido).")

    sesion.tarea(Tarea("analisis", f"Reducir ruido de {bruto.nombre}",
                       lambda contexto: audio_procesado.reducir_ruido(entrada, salida, contexto),
                       prioridad=BANCO_VISIBLE, clave=f"ruido-{id_bruto}"), terminar)
