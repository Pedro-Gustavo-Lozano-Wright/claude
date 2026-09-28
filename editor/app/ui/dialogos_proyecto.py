"""Diálogos del menú Proyecto: idiomas, atajos y mantenimiento."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from editor.app.controladores import proyecto as ctl_proyecto
from editor.app.ui.tema import TEMA, texto, texto_suave
from editor.app.ui.teclado import atajos_por_accion, guardar_atajos

if TYPE_CHECKING:
    from editor.app.ui.ventana import Ventana

NOMBRES_ACCION = {
    "reproducir_pausar": "Reproducir / pausar", "reproducir": "Reproducir (L)",
    "fotograma_anterior": "Fotograma anterior", "fotograma_siguiente": "Fotograma siguiente",
    "segundo_anterior": "Segundo anterior", "segundo_siguiente": "Segundo siguiente",
    "retroceder_segundo": "Retroceder un segundo", "inicio_minuto": "Inicio del minuto",
    "marcar_entrada": "Marcar entrada", "marcar_salida": "Marcar salida", "dividir": "Dividir",
    "marcador": "Marcador", "deseleccionar": "Deseleccionar",
    "herramienta_seleccion": "Herramienta selección", "herramienta_cuchilla": "Herramienta cuchilla",
    "herramienta_ripple": "Herramienta ripple", "herramienta_roll": "Herramienta roll",
    "herramienta_slip": "Herramienta slip", "herramienta_slide": "Herramienta slide",
    "agregar_keyframe": "Keyframe", "deshacer": "Deshacer", "rehacer": "Rehacer",
    "rehacer_alternativo": "Rehacer (alternativo)", "guardar": "Guardar", "copiar": "Copiar",
    "pegar": "Pegar", "duplicar": "Duplicar", "buscar": "Buscar en la timeline", "borrar": "Borrar",
    "ripple_borrar": "Borrar con ripple", "mover_1px": "Mover 1 px", "mover_10px": "Mover 10 px",
    "zoom_timeline_mas": "Acercar timeline", "zoom_timeline_menos": "Alejar timeline",
    "minuto_anterior": "Minuto anterior", "minuto_siguiente": "Minuto siguiente",
}


def _megas(bytes_: int) -> str:
    return f"{bytes_ / 1e9:.2f} GB" if bytes_ >= 1e9 else f"{bytes_ / 1e6:.1f} MB"


def idiomas(app: "Ventana") -> None:
    proyecto = app.sesion.proyecto
    campo = ft.TextField(label="Idiomas (códigos separados por coma; el primero es el principal)",
                         value=", ".join(proyecto.idiomas), autofocus=True, width=460)
    ayuda = texto_suave("Cada idioma es una pista de audio del render. Las capas A se asignan a un idioma "
                        "desde su cabecera en la timeline (* = común a todos).")

    def aceptar() -> None:
        lista = [i for i in (campo.value or "").replace(";", ",").split(",") if i.strip()]
        if ctl_proyecto.cambiar_idiomas(app.sesion, lista):
            app.aviso_breve("Idiomas: " + ", ".join(app.sesion.proyecto.idiomas))
            app.monitor.idioma.options = [ft.DropdownOption(key=i, text=i) for i in app.sesion.proyecto.idiomas]
            app.monitor.idioma.value = app.sesion.estado.idioma_escucha
            app.refrescar()

    app.raiz.dialogo("Idiomas del proyecto", ft.Column([campo, ayuda], tight=True, width=480),
                     [("Aplicar", aceptar), ("Cancelar", None)])


def atajos(app: "Ventana") -> None:
    actuales = atajos_por_accion()
    campos = {
        accion: ft.TextField(value=combinacion, dense=True, width=180, text_size=TEMA.tamano_texto)
        for accion, combinacion in actuales.items()
    }
    filas = [ft.Row([ft.Text(NOMBRES_ACCION.get(a, a), size=TEMA.tamano_texto, width=220), c]) for a, c in campos.items()]
    contenido = ft.Column(
        [texto_suave("Escriba la combinación: Ctrl+Shift+Z, Alt+K, Space, Left, PageUp, Delete… "
                     "(«Flechas» vale por las cuatro)."), *filas],
        scroll=ft.ScrollMode.AUTO, height=460, width=440,
    )

    def aceptar() -> None:
        problemas = guardar_atajos({a: (c.value or "").strip() for a, c in campos.items() if (c.value or "").strip()})
        if problemas:
            app.avisar("No se guardaron los atajos:\n" + "\n".join(problemas))
            return
        app.teclado.recargar()
        app.aviso_breve("Atajos guardados.")

    app.raiz.dialogo("Atajos de teclado", contenido, [("Guardar", aceptar), ("Cancelar", None)])


def mantenimiento(app: "Ventana") -> None:
    sesion = app.sesion
    try:
        tamanos = ctl_proyecto.tamanos(sesion)
        sin_uso = ctl_proyecto.brutos_sin_uso(sesion)
    except OSError as error:
        app.avisar(f"No se pudo revisar el proyecto: {error}")
        return
    nombres = [sesion.proyecto.taller.brutos[i].nombre for i in sin_uso]

    def accion(funcion, exito: str):
        def ejecutar() -> None:
            try:
                resultado = funcion()
            except (RuntimeError, OSError) as error:
                app.avisar(str(error))
                return
            if resultado is False:   # el comando lo rechazó y ya avisó
                return
            app.aviso_breve(exito.format(_megas(resultado) if type(resultado) is int else ""))
            app.refrescar()
        return ejecutar

    contenido = ft.Column(
        [
            *[ft.Row([texto(nombre, width=220), texto_suave(_megas(valor))]) for nombre, valor in tamanos.items()],
            ft.Divider(),
            texto_suave(f"Brutos sin uso ({len(sin_uso)}): " + (", ".join(nombres) if nombres else "ninguno")),
            texto_suave("La caché se regenera sola. La papelera guarda lo que un guardado reemplazó: "
                        "vaciarla borra el historial de deshacer."),
        ],
        tight=True, width=480,
    )
    acciones = [
        ("Vaciar caché", accion(lambda: ctl_proyecto.vaciar_cache(sesion), "Caché vaciada ({})")),
        ("Vaciar papelera", accion(lambda: ctl_proyecto.vaciar_papelera(sesion), "Papelera vaciada ({})")),
    ]
    if sin_uso:
        acciones.append(("Quitar Brutos sin uso", accion(lambda: ctl_proyecto.quitar_brutos(sesion, sin_uso),
                                                         "Brutos quitados; al guardar pasan a la papelera.")))
    acciones.append(("Cerrar", None))
    app.raiz.dialogo("Mantenimiento del proyecto", contenido, acciones)
