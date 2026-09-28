"""Acciones del Taller: Piezas, fps, horneado, colocación (E15) y análisis de medios (E17)."""

from __future__ import annotations

import copy
from fractions import Fraction

import numpy as np

from editor.app.estado import Sesion
from editor.core.comandos.agregar_elemento import AgregarElemento
from editor.core.comandos.fabrica import elemento_desde_bruto, elemento_desde_pieza
from editor.core.comandos.operaciones import ModoColocacion
from editor.core.comandos.taller import AgregarPieza, CambiarRecetaPieza, InterpretarFps, QuitarBruto
from editor.core.espacio.transform import ENCAJAR
from editor.core.modelo.bruto import TipoMedio
from editor.core.modelo.capa import Capa, TipoCapa
from editor.core.modelo.errores import ErrorModelo
from editor.core.proyecto_fs import consultas
from editor.core.modelo.pieza import AudioConformado, MetodoConversionFps, Pieza, TramoFuente
from editor.core.estandar import ASAS_FOTOGRAMAS, FPS
from editor.core.modelo.capitulo import Capitulo
from editor.core.motor.mezclador_audio import Mezclador
from editor.core.servicios import analisis, banco, forma_onda, horneado, importacion, mantenimiento, miniaturas
from editor.core.servicios.importacion import EspacioInsuficiente
from editor.core.tareas.cola import BANCO_VISIBLE, MONITOR, PRERENDER_ACTUAL, Tarea
from editor.core.tiempo.nomenclatura import normalizar_nombre


def crear_pieza(sesion: Sesion, id_bruto: str, entrada: int, salida: int,
                metodo: MetodoConversionFps = MetodoConversionFps.TIEMPO, nombre: str | None = None) -> str | None:
    """Nueva Pieza con un tramo del Bruto en **fotogramas nativos** [entrada, salida)."""
    proyecto = sesion.proyecto
    bruto = proyecto.taller.bruto(id_bruto)
    try:
        pieza = Pieza(
            id=proyecto.nuevo_id(),
            numero=proyecto.taller.siguiente_numero_pieza(),
            nombre=normalizar_nombre(nombre or bruto.nombre),
            tramos=[TramoFuente(id_bruto, entrada, salida)],
            metodo_fps=metodo,
            # Si el método cambia la duración, el audio se estira sin cambiar el tono (E20).
            audio_conformado=AudioConformado.CONSERVAR_TONO,
        )
    except ErrorModelo as error:
        sesion.avisar(str(error))
        return None
    return pieza.id if sesion.ejecutar(AgregarPieza(pieza)) else None


def agregar_tramo(sesion: Sesion, id_pieza: str, id_bruto: str, entrada: int, salida: int) -> bool:
    pieza = sesion.proyecto.taller.pieza(id_pieza)
    return sesion.ejecutar(CambiarRecetaPieza(id_pieza, tramos=pieza.tramos + [TramoFuente(id_bruto, entrada, salida)]))


def cambiar_metodo(sesion: Sesion, id_pieza: str, metodo: MetodoConversionFps) -> bool:
    return sesion.ejecutar(CambiarRecetaPieza(id_pieza, metodo_fps=metodo))


def cambiar_audio_conformado(sesion: Sesion, id_pieza: str, modo: AudioConformado) -> bool:
    return sesion.ejecutar(CambiarRecetaPieza(id_pieza, audio_conformado=modo))


def interpretar_fps(sesion: Sesion, id_bruto: str, fps: Fraction | None) -> bool:
    return sesion.ejecutar(InterpretarFps(id_bruto, fps))


def hornear(sesion: Sesion, id_pieza: str) -> None:
    proyecto = sesion.proyecto
    assert proyecto.raiz is not None
    if sesion.solo_lectura:
        sesion.avisar("El proyecto está abierto en solo lectura: no se puede hornear.")
        return
    raiz = proyecto.raiz
    pieza = copy.deepcopy(proyecto.taller.pieza(id_pieza))
    brutos = copy.deepcopy(proyecto.taller.brutos)
    estandar = proyecto.estandar
    try:
        primero = brutos[pieza.tramos[0].id_bruto]
        fotogramas = pieza.fotogramas_24(brutos) + 2 * ASAS_FOTOGRAMAS
        mantenimiento.comprobar_espacio(raiz, mantenimiento.estimar_video(
            fotogramas, primero.ancho or 1280, primero.alto or 720, primero.tiene_alfa), f"hornear {pieza.nombre}")
    except EspacioInsuficiente as error:
        sesion.avisar(str(error))
        return
    except (KeyError, IndexError):
        pass   # receta incompleta: el propio horneado lo informa

    def terminar(resultado, error) -> None:
        if error is not None:
            sesion.avisar(f"No se pudo hornear {pieza.nombre}: {error}")
            return
        horneado.aplicar_horneado(proyecto, sesion.apertura.estado, id_pieza, resultado, sesion.bus)
        sesion.vista_previa.actualizar_taller(proyecto)
        preparar_vista_previa(sesion, resultado.archivo)
        sesion.avisar(f"{pieza.nombre} horneada (versión {resultado.version}).")

    sesion.tarea(
        Tarea("hornear", f"Hornear {pieza.nombre}",
              lambda contexto: horneado.hornear(raiz, pieza, brutos, estandar, contexto),
              prioridad=PRERENDER_ACTUAL, clave=f"hornear-{id_pieza}"),
        terminar,
    )


def preparar_vista_previa(sesion: Sesion, archivo, al_terminar=None) -> None:
    """Banco, miniaturas y forma de onda de un archivo (tareas de fondo).

    Video: las tres cosas. Imagen: nada (se lee directo). Audio: solo la forma de onda.
    `al_terminar()` corre en el hilo de Flet (la timeline lo usa para redibujar).
    """
    if archivo is None:
        return
    raiz = sesion.proyecto.raiz
    parametros = sesion.proyecto.estandar.banco
    tipo = importacion.tipo_de(archivo)
    if tipo is TipoMedio.IMAGEN:
        return

    def trabajo(contexto):
        if tipo is TipoMedio.VIDEO:
            banco.generar(raiz, archivo, parametros, contexto)
            miniaturas.generar(raiz, archivo)
        forma_onda.generar(raiz, archivo, contexto)
        return archivo

    sesion.tarea(Tarea("banco", f"Vista previa de {archivo.name}", trabajo, prioridad=BANCO_VISIBLE,
                       clave=f"banco-{archivo}"),
                 (lambda _resultado, error: al_terminar() if error is None else None) if al_terminar else None)


# --- E17: análisis en el Taller ---------------------------------------------------------

def detectar_escenas(sesion: Sesion, id_bruto: str, al_terminar) -> None:
    """Cortes de plano del Bruto (fotogramas nativos) → `al_terminar(lista)` en el hilo de Flet."""
    bruto = sesion.proyecto.taller.bruto(id_bruto)
    if bruto.archivo is None or bruto.tipo is not TipoMedio.VIDEO:
        sesion.avisar("Las escenas se buscan en un Bruto de video.")
        return
    ruta = bruto.archivo
    sesion.tarea(Tarea("analisis", f"Escenas de {bruto.nombre}", lambda c: analisis.detectar_escenas(ruta, c),
                       prioridad=BANCO_VISIBLE, clave=f"escenas-{id_bruto}"),
                 lambda resultado, error: sesion.avisar(f"No se pudieron buscar escenas: {error}") if error
                 else al_terminar(resultado))


def detectar_silencios(sesion: Sesion, id_bruto: str, al_terminar) -> None:
    """Tramos en silencio (segundos) → `al_terminar(lista de Silencio)` en el hilo de Flet."""
    bruto = sesion.proyecto.taller.bruto(id_bruto)
    if bruto.archivo is None or not (bruto.tiene_audio or bruto.tipo is TipoMedio.AUDIO):
        sesion.avisar("El Bruto no tiene audio.")
        return
    ruta = bruto.archivo
    sesion.tarea(Tarea("analisis", f"Silencios de {bruto.nombre}", lambda c: analisis.detectar_silencios(ruta, c),
                       prioridad=BANCO_VISIBLE, clave=f"silencios-{id_bruto}"),
                 lambda resultado, error: sesion.avisar(f"No se pudieron buscar silencios: {error}") if error
                 else al_terminar(resultado))


UMBRAL_CONFIANZA = 0.2


def sincronizar_audio(sesion: Sesion, id_elemento: str, id_bruto_audio: str) -> None:
    """Coloca un audio externo (Bruto de audio) alineado con el sonido de un Elemento de la timeline.

    La referencia es lo que suena ese Elemento solo (su mezcla); el desfase sale de la
    correlación de envolventes. El audio se coloca en la capa de audio destino; si
    empieza antes que el Elemento, se recorta su comienzo.
    """
    capitulo_actual = sesion.capitulo
    elemento = capitulo_actual.buscar(id_elemento)
    bruto = sesion.proyecto.taller.bruto(id_bruto_audio)
    if elemento is None or not elemento.suena:
        sesion.avisar("Elija en la timeline un Elemento con sonido como referencia.")
        return
    if bruto.archivo is None or bruto.tipo is not TipoMedio.AUDIO:
        sesion.avisar("El audio externo debe ser un Bruto de audio.")
        return
    solo = Capitulo(numero=capitulo_actual.numero)
    duplicado = copy.deepcopy(elemento)
    duplicado.estado.activo = True
    duplicado.audio.silenciado = False
    solo.contenedor_de(duplicado).elementos[duplicado.id] = duplicado
    mezclador = Mezclador(sesion.vista_previa.resolutor)
    inicio, fin = elemento.inicio, elemento.fin
    ruta = bruto.archivo
    nombre = elemento.nombre

    def trabajo(contexto):
        referencia = mezclador.mezclar(solo, inicio, fin)
        return analisis.desfase_con_archivo(referencia, ruta, contexto)

    def terminar(resultado, error) -> None:
        if error is not None:
            sesion.avisar(f"No se pudo sincronizar: {error}")
            return
        segundos, confianza = resultado
        if confianza < UMBRAL_CONFIANZA:
            sesion.avisar(f"No se encontró coincidencia clara con {nombre} (confianza {confianza:.0%}).")
            return
        colocar_audio_desfasado(sesion, id_bruto_audio, inicio, round(segundos * FPS), confianza)

    sesion.tarea(Tarea("analisis", f"Sincronizar {bruto.nombre} con {nombre}", trabajo,
                       prioridad=BANCO_VISIBLE, clave=f"sincronia-{id_bruto_audio}"), terminar)


def colocar_audio_desfasado(sesion: Sesion, id_bruto: str, inicio_referencia: int, desfase: int,
                            confianza: float = 1.0) -> bool:
    """El instante 0 de la referencia está en `desfase` fotogramas del audio externo."""
    proyecto = sesion.proyecto
    bruto = proyecto.taller.bruto(id_bruto)
    capa = Capa.desde_codigo(sesion.estado.capa_destino_audio)
    inicio = inicio_referencia - desfase
    recorte = max(0, -inicio)
    try:
        elemento = elemento_desde_bruto(proyecto, bruto, capa, max(0, inicio), en_global=sesion.estado.destino_global)
    except ErrorModelo as error:
        sesion.avisar(str(error))
        return False
    if recorte:
        elemento.tiempo.fuente_entrada = recorte
        elemento.tiempo.duracion = max(1, elemento.tiempo.duracion - recorte)
    if sesion.ejecutar(AgregarElemento(sesion.estado.capitulo, elemento)):
        sesion.estado.seleccion = {elemento.id}
        preparar_vista_previa(sesion, bruto.archivo)
        sesion.avisar(f"{bruto.nombre} alineado: desfase {desfase / FPS:+.2f} s (confianza {confianza:.0%}).")
        return True
    return False


def colocar_pieza(sesion: Sesion, id_pieza: str, codigo_capa: str | None = None,
                  modo: ModoColocacion = ModoColocacion.RECHAZAR) -> bool:
    """Coloca la Pieza en el cabezal, en la capa elegida (o la capa destino de la sesión)."""
    proyecto = sesion.proyecto
    pieza = proyecto.taller.pieza(id_pieza)
    capa = Capa.desde_codigo(codigo_capa or sesion.estado.capa_destino)
    try:
        elemento = elemento_desde_pieza(proyecto, pieza, capa, sesion.estado.cabezal, ajuste=ENCAJAR,
                                        en_global=sesion.estado.destino_global)
    except ErrorModelo as error:
        sesion.avisar(str(error))
        return False
    if sesion.ejecutar(AgregarElemento(sesion.estado.capitulo, elemento, modo)):
        sesion.estado.seleccion = {elemento.id}
        return True
    return False


def colocar_bruto(sesion: Sesion, id_bruto: str, codigo_capa: str | None = None,
                  modo: ModoColocacion = ModoColocacion.RECHAZAR) -> bool:
    """Imagen o audio directo desde un Bruto (sin Pieza)."""
    proyecto = sesion.proyecto
    bruto = proyecto.taller.bruto(id_bruto)
    if codigo_capa is None:
        codigo_capa = sesion.estado.capa_destino_audio if bruto.tipo is TipoMedio.AUDIO else "V2"
    capa = Capa.desde_codigo(codigo_capa)
    if bruto.tipo is TipoMedio.AUDIO and capa.tipo is not TipoCapa.AUDIO:
        capa = Capa(TipoCapa.AUDIO, 1)
    try:
        elemento = elemento_desde_bruto(proyecto, bruto, capa, sesion.estado.cabezal, ajuste=ENCAJAR,
                                        en_global=sesion.estado.destino_global)
    except ErrorModelo as error:
        sesion.avisar(str(error))
        return False
    if sesion.ejecutar(AgregarElemento(sesion.estado.capitulo, elemento, modo)):
        sesion.estado.seleccion = {elemento.id}
        preparar_vista_previa(sesion, bruto.archivo)   # forma de onda para la timeline
        return True
    return False


def quitar_bruto(sesion: Sesion, id_bruto: str) -> bool:
    """Quita el Bruto del Taller (se deshace). Al guardar, su archivo pasa a `.papelera/`.

    El comando revisa el capítulo cargado y las Piezas; los demás capítulos se miran en disco.
    """
    assert sesion.proyecto.raiz is not None
    cargados = {c.numero for c in sesion.proyecto.capitulos_cargados()}
    if id_bruto in consultas.fuentes_en_disco(sesion.proyecto.raiz, cargados):
        sesion.avisar("Otro capítulo usa este Bruto; quite primero esos Elementos.")
        return False
    return sesion.ejecutar(QuitarBruto(id_bruto))


_visor = None   # GestorFuentes del visor del Taller (se crea al primer uso)


def fotograma_bruto(sesion: Sesion, id_bruto: str, n: int, al_llegar, ancho: int = 640) -> None:
    """Imagen del fotograma nativo `n` de un Bruto para el visor del Taller (tarea de prioridad 1)."""
    global _visor
    from editor.core.motor.decodificador import GestorFuentes
    from editor.core.servicios.vista_previa import a_jpeg

    bruto = sesion.proyecto.taller.bruto(id_bruto)
    if bruto.archivo is None or bruto.tipo is TipoMedio.AUDIO:
        return
    if _visor is None:
        _visor = GestorFuentes()
    visor = _visor
    alto = max(2, round(ancho * (bruto.alto or 9) / (bruto.ancho or 16)) // 2 * 2)
    ruta = bruto.archivo

    def trabajo(contexto):
        contexto.comprobar()
        imagen = visor.fotograma(ruta, max(0, n), (ancho, alto))
        return a_jpeg(np.ascontiguousarray(imagen[..., :3]), sesion.ajustes.monitor_calidad_pausa_jpeg)

    sesion.tarea(Tarea("visor", "Visor del Taller", trabajo, prioridad=MONITOR, clave="taller-visor"),
                 lambda resultado, error: al_llegar(resultado, n) if error is None and resultado else None)


def cerrar_visor() -> None:
    global _visor
    if _visor is not None:
        _visor.cerrar()
        _visor = None
