"""Hornear una Pieza: tramos → 24 fps → transformación y efectos → archivo (T9.4).

- Cada tramo se decodifica en fotogramas **nativos** de su Bruto (con el fps
  interpretado) y se convierte a 24 fps con el método de la Pieza.
- Asas de 1 s antes del primer tramo y después del último, si el Bruto tiene material.
- Resolución de salida: la del primer tramo, limitada a 2560×1440 (pares).
- Opaco → H.264 CRF 14 `.mp4`; con alfa (Bruto con alfa o croma) → ProRes 4444 `.mov`.
- El archivo se escribe en un temporal y se reemplaza de una vez.

`aplicar_horneado` (hilo principal) registra el resultado: estado automático,
copias actualizadas (fuera del historial: el horneado no se deshace) y eventos.
"""

from __future__ import annotations

import os
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

from editor.core.comandos.actualizar_fuente import actualizar_fuente
from editor.core.estandar import ASAS_SEGUNDOS, Estandar
from editor.core.eventos import BusEventos, PiezaHorneada, ProyectoModificado
from editor.core.modelo.bruto import Bruto
from editor.core.modelo.pieza import AudioConformado, Horneado, Pieza
from editor.core.modelo.proyecto import Proyecto
from editor.core.motor.codificador import Codificador, PerfilAudio, PerfilVideo
from editor.core.motor.conversion_fps import convertir, factor_audio, fotogramas_salida
from editor.core.motor.decodificador import FuenteVideo
from editor.core.motor.efectos import ContextoEfecto, aplicar_efectos
from editor.core.motor.estiramiento import estirar
from editor.core.motor.mezclador_audio import FRECUENCIA, FuenteAudio
from editor.core.proyecto_fs import automatico, estructura
from editor.core.proyecto_fs.estado_disco import EstadoDisco
from editor.core.tareas.cola import Contexto
from editor.core.utiles.matematicas import redondear_par


class ErrorHorneado(RuntimeError):
    pass


def _tamano_salida(bruto: Bruto, estandar: Estandar) -> tuple[int, int]:
    ancho, alto = bruto.ancho, bruto.alto
    factor = min(1.0, estandar.pieza.ancho_maximo / ancho, estandar.pieza.alto_maximo / alto)
    return redondear_par(ancho * factor), redondear_par(alto * factor)


def hornear(raiz: Path, pieza: Pieza, brutos: dict[str, Bruto], estandar: Estandar, contexto: Contexto) -> Horneado:
    """Tarea de fondo. `pieza` y `brutos` son copias (instantánea)."""
    if not pieza.tramos:
        raise ErrorHorneado("La Pieza no tiene tramos.")
    for tramo in pieza.tramos:
        bruto = brutos.get(tramo.id_bruto)
        if bruto is None or bruto.fps is None:
            raise ErrorHorneado(f"El Bruto {tramo.id_bruto} no existe o no tiene fps.")
    primero = brutos[pieza.tramos[0].id_bruto]
    ancho, alto = _tamano_salida(primero, estandar)
    con_alfa = any(brutos[t.id_bruto].tiene_alfa for t in pieza.tramos) or any(
        e.tipo == "croma" and e.activo for e in pieza.efectos
    )
    con_audio = any(brutos[t.id_bruto].tiene_audio for t in pieza.tramos)
    perfil = PerfilVideo.prores_4444() if con_alfa else PerfilVideo.h264(estandar.pieza.crf_opaco, "medium")
    version = pieza.version + 1
    extension = perfil.contenedor
    nueva = replace(pieza, horneado=Horneado(version, extension, ancho, alto, 0))
    destino = estructura.ruta_horneado(raiz, nueva)
    assert destino is not None
    temporal = destino.with_name(f".{destino.stem}.parcial.{extension}")
    audio_perfil = PerfilAudio("pcm_s16le" if extension == "mov" else "aac")

    total_nativos = sum(t.fotogramas_nativos for t in pieza.tramos)
    procesados = 0
    escritos = 0
    asas_inicio = asas_fin = 0
    audio_partes: list[np.ndarray] = []
    transformar = not pieza.espacio.es_identidad or pieza.espacio.opacidad < 1
    matriz = np.array(pieza.espacio.matriz().como_lista(), dtype=np.float64) if transformar else None

    with Codificador(temporal, ancho, alto, perfil, [(audio_perfil, None)] if con_audio else None) as salida:
        for indice, tramo in enumerate(pieza.tramos):
            bruto = brutos[tramo.id_bruto]
            fps = Fraction(bruto.fps)  # type: ignore[arg-type]
            asa = round(fps * ASAS_SEGUNDOS)
            antes = min(tramo.entrada, asa) if indice == 0 else 0
            despues = min(max(0, bruto.fotogramas_nativos - tramo.salida), asa) if indice == len(pieza.tramos) - 1 else 0
            desde, hasta = tramo.entrada - antes, tramo.salida + despues
            ruta = estructura.ruta_bruto(raiz, bruto)
            fuente = FuenteVideo(ruta)

            encaje = _encaje(bruto, ancho, alto)

            def cuadros():
                nonlocal procesados
                for n in range(desde, hasta):
                    if encaje is None:
                        imagen = fuente.fotograma(n, (ancho, alto))
                    else:
                        # Otra relación de aspecto que el primer tramo: se encaja con bandas, sin estirar.
                        imagen = _con_bandas(fuente.fotograma(n, encaje), ancho, alto)
                    procesados += 1
                    if procesados % 24 == 0:
                        contexto.progreso(0.95 * procesados / max(1, total_nativos), f"Horneando {pieza.nombre}")
                    yield float((n - desde) / fps), imagen

            try:
                for imagen in convertir(cuadros(), pieza.metodo_fps, float((hasta - desde) / fps)):
                    if transformar or pieza.efectos:
                        imagen = _procesar(imagen, pieza, matriz, ancho, alto)
                    salida.escribir_video(imagen if con_alfa else imagen[..., :3])
                    escritos += 1
            finally:
                fuente.cerrar()
            if indice == 0:
                asas_inicio = fotogramas_salida(antes, fps, pieza.metodo_fps) if antes else 0
            if indice == len(pieza.tramos) - 1:
                asas_fin = fotogramas_salida(despues, fps, pieza.metodo_fps) if despues else 0

            if con_audio:
                audio_partes.append(_audio_tramo(ruta, bruto, desde, hasta, fps, pieza))
        if con_audio:
            muestras = np.concatenate(audio_partes, axis=1)
            objetivo = escritos * (FRECUENCIA // 24)
            muestras = _ajustar_largo(muestras, objetivo)
            salida.escribir_audio(muestras)

    os.replace(temporal, destino)
    contexto.progreso(1.0, f"{pieza.nombre} horneada")
    return Horneado(
        version=version,
        extension=extension,
        ancho=ancho,
        alto=alto,
        fotogramas=escritos,
        asas_inicio=asas_inicio,
        asas_fin=asas_fin,
        tiene_alfa=con_alfa,
        tiene_audio=con_audio,
        archivo=destino,
    )


def _procesar(imagen: np.ndarray, pieza: Pieza, matriz, ancho: int, alto: int) -> np.ndarray:
    flotante = imagen.astype(np.float32) / 255.0
    if pieza.efectos:
        flotante = aplicar_efectos(flotante, pieza.efectos, 0, ContextoEfecto())
    if matriz is not None:
        flotante[..., :3] *= flotante[..., 3:4]
        flotante = cv2.warpAffine(flotante, matriz, (ancho, alto), flags=cv2.INTER_LANCZOS4,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        flotante *= pieza.espacio.opacidad
        alfa = flotante[..., 3:4]
        flotante[..., :3] = np.divide(flotante[..., :3], alfa, out=np.zeros_like(flotante[..., :3]), where=alfa > 1e-6)
    return (np.clip(flotante, 0, 1) * 255 + 0.5).astype(np.uint8)


def _encaje(bruto: Bruto, ancho: int, alto: int) -> tuple[int, int] | None:
    """Tamaño que conserva la relación de aspecto del Bruto dentro de ancho×alto; None si ya coincide."""
    if not bruto.ancho or not bruto.alto:
        return None
    escala = min(ancho / bruto.ancho, alto / bruto.alto)
    tamano = (max(2, round(bruto.ancho * escala)), max(2, round(bruto.alto * escala)))
    return None if abs(tamano[0] - ancho) <= 2 and abs(tamano[1] - alto) <= 2 else tamano


def _con_bandas(imagen: np.ndarray, ancho: int, alto: int) -> np.ndarray:
    """Centra la imagen en un lienzo negro opaco de ancho×alto (RGBA)."""
    lienzo = np.zeros((alto, ancho, 4), dtype=np.uint8)
    lienzo[..., 3] = 255
    y = (alto - imagen.shape[0]) // 2
    x = (ancho - imagen.shape[1]) // 2
    lienzo[y: y + imagen.shape[0], x: x + imagen.shape[1]] = imagen
    return lienzo


def _audio_tramo(ruta: Path, bruto: Bruto, desde: int, hasta: int, fps: Fraction, pieza: Pieza) -> np.ndarray:
    segundos_inicio = float(desde / fps)
    segundos = float((hasta - desde) / fps)
    muestras = FuenteAudio(ruta).leer(round(segundos_inicio * FRECUENCIA), round(segundos * FRECUENCIA))
    factor = factor_audio(fps, pieza.metodo_fps)
    if factor == 1.0:
        return muestras
    largo = round(muestras.shape[1] * factor)
    if pieza.audio_conformado is AudioConformado.SILENCIAR:
        return np.zeros((2, largo), dtype=np.float32)
    if pieza.audio_conformado is AudioConformado.CONSERVAR_TONO:
        return estirar(muestras, largo)
    return _ajustar_largo(muestras, largo)


def _ajustar_largo(muestras: np.ndarray, largo: int) -> np.ndarray:
    if muestras.shape[1] == largo:
        return muestras
    if muestras.shape[1] == 0:
        return np.zeros((2, largo), dtype=np.float32)
    posiciones = np.linspace(0, muestras.shape[1] - 1, largo)
    indices = np.arange(muestras.shape[1])
    return np.vstack([np.interp(posiciones, indices, muestras[c]) for c in range(2)]).astype(np.float32)


def aplicar_horneado(
    proyecto: Proyecto,
    estado: EstadoDisco,
    id_pieza: str,
    horneado: Horneado,
    bus: BusEventos | None = None,
) -> None:
    """Hilo principal: registra el horneado y actualiza sus copias en los capítulos."""
    pieza = proyecto.taller.pieza(id_pieza)
    anterior = pieza.horneado
    asas_anteriores = anterior.asas_inicio if anterior is not None else horneado.asas_inicio
    if anterior is not None and anterior.extension != horneado.extension and proyecto.raiz is not None:
        # Cambió el formato (p. ej. .mp4 → .mov por un croma): el archivo viejo ya no sirve.
        viejo = estructura.ruta_horneado(proyecto.raiz, pieza)
        if viejo is not None and viejo != horneado.archivo:
            viejo.unlink(missing_ok=True)
    pieza.horneado = horneado
    pieza.receta_modificada = False
    automatico.guardar_horneado(proyecto, estado, pieza)
    capitulos = {c.capitulo for c in estado.copias_piezas.get(id_pieza, [])}
    capitulos |= {u.capitulo for u in proyecto.referencias.ubicaciones_de_fuente(id_pieza)}
    capitulos = {n for n in capitulos if proyecto.existe_capitulo(n)}
    if capitulos:
        # Fuera del historial: el horneado es estado automático y no se deshace (PROJECT.md, 22.7).
        actualizar_fuente(pieza, asas_anteriores, sorted(capitulos)).ejecutar(proyecto)
        if bus is not None:
            bus.publicar(ProyectoModificado())
    if bus is not None:
        bus.publicar(PiezaHorneada(id_pieza, horneado.version))
