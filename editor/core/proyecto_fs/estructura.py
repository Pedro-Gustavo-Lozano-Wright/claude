"""Estructura en disco: rutas de todo el proyecto y creación de carpetas (T5.4).

Las rutas se calculan siempre desde el modelo y la nomenclatura; nunca se
escriben a mano en otro módulo.
"""

from __future__ import annotations

from pathlib import Path

from editor.core.estandar import MINUTOS_POR_CAPITULO, Estandar
from editor.core.modelo.bruto import Bruto
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.pieza import Pieza
from editor.core.modelo.proyecto import Proyecto
from editor.core.modelo.short import Short
from editor.core.proyecto_fs import guion
from editor.core.proyecto_fs.manifiestos import capitulo_a_datos, minuto_a_datos, proyecto_a_datos
from editor.core.proyecto_fs.serializacion import escribir_json_atomico, escribir_texto_atomico
from editor.core.tiempo import nomenclatura as nom


# --- Rutas -------------------------------------------------------------------------

def ruta_manifiesto_proyecto(raiz: Path) -> Path:
    return raiz / nom.ARCHIVO_PROYECTO


def ruta_bruto(raiz: Path, bruto: Bruto) -> Path:
    return raiz / nom.CARPETA_BRUTOS / bruto.tipo.subcarpeta / bruto.nombre_archivo().archivo


def carpeta_pieza(raiz: Path, pieza: Pieza) -> Path:
    return raiz / nom.CARPETA_TALLER / pieza.nombre_archivo().carpeta


def ruta_manifiesto_pieza(raiz: Path, pieza: Pieza) -> Path:
    return carpeta_pieza(raiz, pieza) / nom.ARCHIVO_PIEZA


def ruta_horneado(raiz: Path, pieza: Pieza) -> Path | None:
    if pieza.horneado is None:
        return None
    return carpeta_pieza(raiz, pieza) / pieza.nombre_archivo().archivo(pieza.horneado.extension)


def carpeta_de_elemento(raiz: Path, capitulo: int, elemento: Elemento) -> Path:
    if elemento.en_global:
        return nom.carpeta_global(raiz, capitulo)
    return nom.carpeta_minuto(raiz, capitulo, elemento.minuto_inicio)


def ruta_contenido(raiz: Path, capitulo: int, elemento: Elemento) -> Path | None:
    """Archivo de medios del Elemento; None para textos (su gemelo es el contenido)."""
    if elemento.es_texto:
        return None
    return carpeta_de_elemento(raiz, capitulo, elemento) / elemento.nombre_archivo().archivo


def ruta_gemelo(raiz: Path, capitulo: int, elemento: Elemento) -> Path:
    return carpeta_de_elemento(raiz, capitulo, elemento) / elemento.nombre_archivo().gemelo


def ruta_manifiesto_capitulo(raiz: Path, capitulo: int) -> Path:
    return nom.carpeta_capitulo(raiz, capitulo) / nom.ARCHIVO_CAPITULO


def ruta_manifiesto_minuto(raiz: Path, capitulo: int, minuto: int) -> Path:
    return nom.carpeta_minuto(raiz, capitulo, minuto) / nom.ARCHIVO_MINUTO


def ruta_guion(raiz: Path, capitulo: int, minuto: int) -> Path:
    return nom.carpeta_minuto(raiz, capitulo, minuto) / nom.ARCHIVO_GUION


def ruta_receta_short(raiz: Path, capitulo: int, short: Short) -> Path:
    return nom.carpeta_shorts(raiz, capitulo) / short.nombre_archivo().receta


def relativa(raiz: Path, ruta: Path) -> str:
    return ruta.relative_to(raiz).as_posix()


# --- Creación ------------------------------------------------------------------------

class ProyectoExistente(FileExistsError):
    pass


def crear_proyecto(
    raiz: Path,
    nombre: str | None = None,
    estandar: Estandar | None = None,
    idiomas: list[str] | None = None,
) -> Proyecto:
    """Crea la carpeta del proyecto con su estructura base y devuelve el Proyecto."""
    raiz = raiz.expanduser().resolve()
    if ruta_manifiesto_proyecto(raiz).exists():
        raise ProyectoExistente(f"Ya hay un proyecto en {raiz}.")
    if raiz.exists() and any(raiz.iterdir()):
        raise ProyectoExistente(f"La carpeta {raiz} no está vacía.")
    proyecto = Proyecto(
        nombre=nombre or raiz.name,
        raiz=raiz,
        estandar=estandar or Estandar(),
        idiomas=idiomas or ["es"],
    )
    crear_carpetas_proyecto(raiz)
    escribir_json_atomico(ruta_manifiesto_proyecto(raiz), proyecto_a_datos(proyecto))
    return proyecto


def crear_carpetas_proyecto(raiz: Path) -> None:
    for sub in nom.SUBCARPETAS_BRUTOS:
        (raiz / nom.CARPETA_BRUTOS / sub).mkdir(parents=True, exist_ok=True)
    for sub in nom.SUBCARPETAS_RECURSOS:
        (raiz / nom.CARPETA_RECURSOS / sub).mkdir(parents=True, exist_ok=True)
    for carpeta in (nom.CARPETA_TALLER, nom.CARPETA_DIARIO, nom.CARPETA_AUTOSAVE, nom.CARPETA_CACHE, nom.CARPETA_PAPELERA):
        (raiz / carpeta).mkdir(parents=True, exist_ok=True)


def crear_carpetas_capitulo(raiz: Path, capitulo: Capitulo) -> None:
    """Crea `capNNNN/` con min00–min23, global, render y shorts, y sus manifiestos."""
    numero = capitulo.numero
    for minuto in range(MINUTOS_POR_CAPITULO):
        nom.carpeta_minuto(raiz, numero, minuto).mkdir(parents=True, exist_ok=True)
    for carpeta in (nom.carpeta_global, nom.carpeta_render, nom.carpeta_shorts):
        carpeta(raiz, numero).mkdir(parents=True, exist_ok=True)
    escribir_json_atomico(ruta_manifiesto_capitulo(raiz, numero), capitulo_a_datos(capitulo))
    for minuto in capitulo.minutos:
        escribir_json_atomico(ruta_manifiesto_minuto(raiz, numero, minuto.numero), minuto_a_datos(minuto))
        escribir_texto_atomico(ruta_guion(raiz, numero, minuto.numero), guion.generar(capitulo, minuto.numero))


def crear_capitulo(proyecto: Proyecto, numero: int | None = None, titulo: str = "") -> Capitulo:
    """Crea un capítulo en el modelo y en disco, y actualiza `_proyecto.json`."""
    if proyecto.raiz is None:
        raise ValueError("El proyecto no tiene carpeta.")
    capitulo = proyecto.crear_capitulo(numero, titulo)
    crear_carpetas_capitulo(proyecto.raiz, capitulo)
    escribir_json_atomico(ruta_manifiesto_proyecto(proyecto.raiz), proyecto_a_datos(proyecto))
    return capitulo
