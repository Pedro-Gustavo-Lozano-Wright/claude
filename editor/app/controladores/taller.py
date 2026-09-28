"""Acciones del Taller: Piezas, interpretación de fps, horneado y colocación (E15)."""

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
from editor.core.modelo.pieza import MetodoConversionFps, Pieza, TramoFuente
from editor.core.servicios import banco, forma_onda, horneado, miniaturas
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


def preparar_vista_previa(sesion: Sesion, archivo) -> None:
    """Banco, miniaturas y forma de onda de un archivo horneado (tareas de fondo)."""
    if archivo is None:
        return
    raiz = sesion.proyecto.raiz
    parametros = sesion.proyecto.estandar.banco

    def trabajo(contexto):
        banco.generar(raiz, archivo, parametros, contexto)
        miniaturas.generar(raiz, archivo)
        forma_onda.generar(raiz, archivo, contexto)
        return archivo

    sesion.tarea(Tarea("banco", f"Vista previa de {archivo.name}", trabajo, prioridad=BANCO_VISIBLE,
                       clave=f"banco-{archivo}"))


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
        codigo_capa = "A1" if bruto.tipo is TipoMedio.AUDIO else "V2"
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
        return True
    return False


def quitar_bruto(sesion: Sesion, id_bruto: str) -> bool:
    """Quita el Bruto del Taller (se deshace). Al guardar, su archivo pasa a `.papelera/`."""
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
