"""Mezclador de audio.

Rejilla exacta: 48 000 / 24 = **2000 muestras por fotograma**, así audio y
video se alinean sin redondeos.

Para un rango de fotogramas del capítulo mezcla todo lo que suena
(`Capitulo.sonoros_activos_en`, que respeta silencio, solo e idioma):
lee el tramo de cada fuente, lo adapta a la velocidad del Elemento, aplica
volumen y paneo con rampas por muestra (sin clics), fundidos y cruces por
transición, suma y limita suavemente.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Callable

import av
import numpy as np

from editor.core.estandar import FPS
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.motor.estiramiento import estirar

FRECUENCIA = 48_000
MUESTRAS_POR_FOTOGRAMA = FRECUENCIA // FPS  # 2000
BLOQUE_SEGUNDOS = 10

Resolutor = Callable[[Elemento], Path | None]


class FuenteAudio:
    """Audio de un archivo, decodificado por bloques de 10 s a 48 kHz estéreo float32."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self._bloques: OrderedDict[int, np.ndarray] = OrderedDict()
        self._candado = threading.Lock()
        with av.open(str(ruta)) as contenedor:
            self.tiene_audio = bool(contenedor.streams.audio)

    def _bloque(self, indice: int) -> np.ndarray:
        if indice in self._bloques:
            self._bloques.move_to_end(indice)
            return self._bloques[indice]
        inicio = indice * BLOQUE_SEGUNDOS
        largo = BLOQUE_SEGUNDOS * FRECUENCIA
        datos = np.zeros((2, largo), dtype=np.float32)
        with av.open(str(self.ruta)) as contenedor:
            if contenedor.streams.audio:
                stream = contenedor.streams.audio[0]
                remuestreador = av.AudioResampler(format="fltp", layout="stereo", rate=FRECUENCIA)
                if inicio > 0:
                    contenedor.seek(int(inicio / stream.time_base), stream=stream, backward=True)
                escrito = 0
                for cuadro in contenedor.decode(stream):
                    comienzo = float(cuadro.pts * stream.time_base) if cuadro.pts is not None else inicio
                    for salida in remuestreador.resample(cuadro):
                        muestras = salida.to_ndarray()
                        if muestras.shape[0] == 1:
                            muestras = np.vstack([muestras, muestras])
                        desplazamiento = round((comienzo - inicio) * FRECUENCIA) if escrito == 0 else escrito
                        if desplazamiento < 0:
                            muestras = muestras[:, -desplazamiento:]
                            desplazamiento = 0
                        fin = min(largo, desplazamiento + muestras.shape[1])
                        if fin > desplazamiento:
                            datos[:, desplazamiento:fin] = muestras[:, : fin - desplazamiento]
                        escrito = max(escrito, fin)
                        comienzo += muestras.shape[1] / FRECUENCIA
                    if escrito >= largo:
                        break
        self._bloques[indice] = datos
        while len(self._bloques) > 6:
            self._bloques.popitem(last=False)
        return datos

    def leer(self, desde: int, cantidad: int) -> np.ndarray:
        """Muestras [desde, desde + cantidad) a 48 kHz; silencio fuera del archivo."""
        resultado = np.zeros((2, cantidad), dtype=np.float32)
        if cantidad <= 0 or not self.tiene_audio:
            return resultado
        largo = BLOQUE_SEGUNDOS * FRECUENCIA
        with self._candado:
            posicion = desde
            while posicion < desde + cantidad:
                if posicion < 0:
                    salto = min(-posicion, desde + cantidad - posicion)
                    posicion += salto
                    continue
                indice, dentro = divmod(posicion, largo)
                trozo = min(largo - dentro, desde + cantidad - posicion)
                bloque = self._bloque(indice)
                resultado[:, posicion - desde: posicion - desde + trozo] = bloque[:, dentro: dentro + trozo]
                posicion += trozo
        return resultado


class Mezclador:
    def __init__(self, resolver: Resolutor) -> None:
        self.resolver = resolver
        self._fuentes: OrderedDict[Path, FuenteAudio] = OrderedDict()
        self._candado = threading.Lock()

    def _fuente(self, ruta: Path) -> FuenteAudio:
        with self._candado:
            if ruta not in self._fuentes:
                self._fuentes[ruta] = FuenteAudio(ruta)
                while len(self._fuentes) > 32:
                    self._fuentes.popitem(last=False)
            self._fuentes.move_to_end(ruta)
            return self._fuentes[ruta]

    def olvidar(self, ruta: Path | None = None) -> None:
        with self._candado:
            if ruta is None:
                self._fuentes.clear()
            else:
                self._fuentes.pop(ruta, None)

    def mezclar(self, capitulo: Capitulo, inicio: int, fin: int, idioma: str | None = None) -> np.ndarray:
        """Mezcla estéreo float32 (2, (fin-inicio)·2000) del rango [inicio, fin) del capítulo."""
        total = (fin - inicio) * MUESTRAS_POR_FOTOGRAMA
        mezcla = np.zeros((2, total), dtype=np.float32)
        candidatos = {
            e.id: e for e in list(capitulo.elementos_de_minutos()) + list(capitulo.global_)
            if e.suena and e.inicio < fin and inicio < e.fin and capitulo.se_oye(e, idioma)
        }
        for elemento in candidatos.values():
            ruta = self.resolver(elemento)
            if ruta is None:
                continue
            a = max(inicio, elemento.inicio)
            b = min(fin, elemento.fin)
            senal = self._senal(elemento, ruta, a, b)
            senal = self._envolvente(capitulo, elemento, senal, a, b)
            desde = (a - inicio) * MUESTRAS_POR_FOTOGRAMA
            mezcla[:, desde: desde + senal.shape[1]] += senal
        return limitar(mezcla)

    def _senal(self, elemento: Elemento, ruta: Path, a: int, b: int) -> np.ndarray:
        cantidad = (b - a) * MUESTRAS_POR_FOTOGRAMA
        tiempo = elemento.tiempo
        if tiempo.congelado:
            return np.zeros((2, cantidad), dtype=np.float32)
        velocidad = abs(tiempo.velocidad)
        fuente = self._fuente(ruta)
        if elemento.con_rampa:
            return self._senal_rampa(elemento, fuente, a, b)
        inicio_fuente = tiempo.fuente_entrada * MUESTRAS_POR_FOTOGRAMA + round((a - elemento.inicio) * velocidad * MUESTRAS_POR_FOTOGRAMA)
        if velocidad == 1.0 and tiempo.velocidad > 0:
            return fuente.leer(inicio_fuente, cantidad)
        largo_fuente = max(1, round(cantidad * velocidad))
        if tiempo.velocidad < 0:
            final = (tiempo.fuente_entrada + tiempo.fotogramas_fuente_usados) * MUESTRAS_POR_FOTOGRAMA
            inicio_fuente = final - round((a - elemento.inicio) * velocidad * MUESTRAS_POR_FOTOGRAMA) - largo_fuente
            original = fuente.leer(inicio_fuente, largo_fuente)[:, ::-1]
        else:
            original = fuente.leer(inicio_fuente, largo_fuente)
        # Velocidad constante: se conserva el tono (WSOLA); fuera de 0,5–2× se remuestrea.
        return estirar(original, cantidad)

    @staticmethod
    def _senal_rampa(elemento: Elemento, fuente: "FuenteAudio", a: int, b: int) -> np.ndarray:
        """Rampa de velocidad: cada muestra lee la posición que da la integral de la velocidad.

        El tono sigue a la velocidad (como en los editores al hacer una rampa)."""
        cantidad = (b - a) * MUESTRAS_POR_FOTOGRAMA
        bordes = np.arange(a, b + 1, dtype=np.float64)
        avance = np.array([elemento.avance_fuente(f - elemento.inicio) for f in bordes]) * MUESTRAS_POR_FOTOGRAMA
        posiciones = np.interp(np.linspace(0, len(bordes) - 1, cantidad), np.arange(len(bordes)), avance)
        base = elemento.tiempo.fuente_entrada * MUESTRAS_POR_FOTOGRAMA
        desde = int(np.floor(posiciones[0])) if cantidad else 0
        largo = int(np.ceil(posiciones[-1])) - desde + 2 if cantidad else 0
        original = fuente.leer(base + desde, max(1, largo))
        indices = np.arange(original.shape[1])
        relativas = posiciones - desde
        return np.vstack([np.interp(relativas, indices, original[c]) for c in range(2)]).astype(np.float32)

    def _envolvente(self, capitulo: Capitulo, elemento: Elemento, senal: np.ndarray, a: int, b: int) -> np.ndarray:
        # Volumen y paneo evaluados en cada borde de fotograma e interpolados por muestra.
        bordes = np.arange(a, b + 1, dtype=np.float64)
        volumen = np.array([elemento.volumen_en(f) for f in bordes], dtype=np.float32)
        paneo = np.array([elemento.paneo_en(f) for f in bordes], dtype=np.float32)
        volumen *= self._cruce(capitulo, elemento, bordes)
        muestras = np.linspace(0, len(bordes) - 1, senal.shape[1], dtype=np.float32)
        indices = np.arange(len(bordes), dtype=np.float32)
        volumen_muestra = np.interp(muestras, indices, volumen)
        paneo_muestra = np.interp(muestras, indices, paneo)
        angulo = (paneo_muestra + 1) * np.pi / 4  # paneo de potencia constante
        senal[0] *= volumen_muestra * np.cos(angulo) * np.sqrt(2)
        senal[1] *= volumen_muestra * np.sin(angulo) * np.sqrt(2)
        return senal

    @staticmethod
    def _cruce(capitulo: Capitulo, elemento: Elemento, bordes: np.ndarray) -> np.ndarray:
        """Fundido cruzado con el vecino de la misma capa durante una transición."""
        factor = np.ones_like(bordes, dtype=np.float32)
        transicion = elemento.transicion_entrada
        if transicion is not None:
            local = bordes - elemento.inicio
            factor *= np.clip(local / transicion.duracion, 0, 1).astype(np.float32)
        fuente = capitulo.global_ if elemento.en_global else capitulo.elementos_de_minutos()
        for otro in fuente:
            siguiente = otro.transicion_entrada
            if (otro.id != elemento.id and otro.capa == elemento.capa and siguiente is not None
                    and elemento.inicio < otro.inicio < elemento.fin):
                local = bordes - otro.inicio
                factor *= (1 - np.clip(local / siguiente.duracion, 0, 1)).astype(np.float32)
        return factor


def limitar(senal: np.ndarray, umbral: float = 0.9) -> np.ndarray:
    """Limitador suave: lineal hasta el umbral, curva tanh por encima (sin recortes duros)."""
    magnitud = np.abs(senal)
    encima = magnitud > umbral
    if np.any(encima):
        resto = 1 - umbral
        senal = senal.copy()
        senal[encima] = np.sign(senal[encima]) * (umbral + resto * np.tanh((magnitud[encima] - umbral) / resto))
    return senal
