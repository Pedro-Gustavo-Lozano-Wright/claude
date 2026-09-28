"""Abrir proyectos y cargar capítulos desde el disco.

- Abrir lee `_proyecto.json` y el Taller, y deja inyectado en el Proyecto un
  cargador de capítulos: cada capítulo se lee recién cuando se necesita.
- Cargar un capítulo lee sus minutos, Global y Shorts, y rescata todo lo
  posible: gemelos faltantes, medios fuera de línea, archivos fuera de su
  carpeta, IDs duplicados. Nada se borra ni se renombra al leer; lo que haya que
  corregir lo hace el siguiente guardado.
- Todo lo encontrado queda en un `Informe`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.composicion import buscar_solape
from editor.core.modelo.elemento import Elemento
from editor.core.modelo.proyecto import Proyecto
from editor.core.modelo.taller import Taller
from editor.core.proyecto_fs import estructura
from editor.core.proyecto_fs.bloqueo import Bloqueo, InfoBloqueo
from editor.core.proyecto_fs.diario import Diario
from editor.core.proyecto_fs.estado_disco import EstadoDisco, Firma, RegistroArchivo, RegistroElemento
from editor.core.proyecto_fs.gemelo import (
    elemento_desde_datos,
    extension_de_medio,
    leer_gemelo,
    short_desde_datos,
)
from editor.core.proyecto_fs.manifiestos import (
    aplicar_datos_capitulo,
    aplicar_datos_minuto,
    aplicar_datos_renders,
    horneado_desde_datos,
    pieza_desde_datos,
    proyecto_desde_datos,
)
from editor.core.proyecto_fs.serializacion import huella, huella_texto, leer_json
from editor.core.tiempo import nomenclatura as nom
from editor.core.tiempo.nomenclatura import NombreElemento, NombreInvalido, NombreShort

registro = logging.getLogger(__name__)


class NoEsProyecto(FileNotFoundError):
    pass


@dataclass
class Informe:
    capitulos_cargados: list[int] = field(default_factory=list)
    capitulos_sin_indice: list[int] = field(default_factory=list)
    elementos: int = 0
    shorts: int = 0
    fuera_de_linea: list[str] = field(default_factory=list)
    gemelos_faltantes: list[str] = field(default_factory=list)
    fuera_de_carpeta: list[str] = field(default_factory=list)
    no_reconocidos: list[str] = field(default_factory=list)
    solapes: list[str] = field(default_factory=list)
    ids_reasignados: list[str] = field(default_factory=list)
    brutos_faltantes: list[str] = field(default_factory=list)
    brutos_sin_registrar: list[str] = field(default_factory=list)
    taller_sin_receta: list[str] = field(default_factory=list)
    piezas_sin_horneado: list[str] = field(default_factory=list)
    diario_recuperado: int = 0
    bloqueo_huerfano: InfoBloqueo | None = None

    @property
    def avisos(self) -> int:
        return sum(len(lista) for lista in (
            self.fuera_de_linea, self.gemelos_faltantes, self.fuera_de_carpeta, self.no_reconocidos,
            self.solapes, self.ids_reasignados, self.brutos_faltantes, self.brutos_sin_registrar,
            self.taller_sin_receta,
        ))

    def resumen(self) -> str:
        lineas = [
            f"Capítulos cargados: {len(self.capitulos_cargados)}",
            f"Elementos: {self.elementos} · Shorts: {self.shorts}",
        ]
        secciones = (
            ("Capítulos encontrados sin estar en el índice", self.capitulos_sin_indice),
            ("Medios fuera de línea", self.fuera_de_linea),
            ("Gemelos faltantes (rescatados con el nombre)", self.gemelos_faltantes),
            ("Archivos fuera de su carpeta (se moverán al guardar)", self.fuera_de_carpeta),
            ("Archivos no reconocidos (no se tocan)", self.no_reconocidos),
            ("Solapamientos en una misma capa", self.solapes),
            ("IDs duplicados reasignados", self.ids_reasignados),
            ("Brutos faltantes", self.brutos_faltantes),
            ("Archivos en brutos/ sin registrar (importados sin guardar)", self.brutos_sin_registrar),
            ("Carpetas del Taller sin _pieza.json (Piezas sin guardar)", self.taller_sin_receta),
            ("Piezas sin hornear", self.piezas_sin_horneado),
        )
        for titulo, lista in secciones:
            if lista:
                lineas.append(f"{titulo}: {len(lista)}")
                lineas.extend(f"  · {item}" for item in lista[:50])
                if len(lista) > 50:
                    lineas.append(f"  … y {len(lista) - 50} más")
        if self.diario_recuperado:
            lineas.append(f"Guardado interrumpido completado: {self.diario_recuperado} operaciones")
        if self.bloqueo_huerfano is not None:
            lineas.append(f"Bloqueo huérfano recuperado (PID {self.bloqueo_huerfano.pid})")
        return "\n".join(lineas)


@dataclass
class Apertura:
    proyecto: Proyecto
    estado: EstadoDisco
    informe: Informe
    bloqueo: Bloqueo | None      # None si se abrió en solo lectura
    solo_lectura: bool

    def cerrar(self) -> None:
        if self.bloqueo is not None:
            self.bloqueo.liberar()


# --- Abrir ---------------------------------------------------------------------------

def es_proyecto(raiz: Path) -> bool:
    return estructura.ruta_manifiesto_proyecto(raiz).exists()


def abrir_proyecto(raiz: Path, solo_lectura: bool = False) -> Apertura:
    """Abre un proyecto. Lanza `ProyectoBloqueado` si otra instancia lo tiene y no es solo lectura."""
    raiz = raiz.expanduser().resolve()
    if not es_proyecto(raiz):
        raise NoEsProyecto(f"{raiz} no es un proyecto (falta {nom.ARCHIVO_PROYECTO}).")

    informe = Informe()
    bloqueo: Bloqueo | None = None
    if not solo_lectura:
        bloqueo = Bloqueo(raiz)
        bloqueo.adquirir()
        informe.bloqueo_huerfano = bloqueo.huerfano_recuperado
        try:
            informe.diario_recuperado = Diario(raiz).recuperar()
        except Exception:
            bloqueo.liberar()
            raise

    try:
        estado = EstadoDisco(raiz=raiz)
        ruta_manifiesto = estructura.ruta_manifiesto_proyecto(raiz)
        datos_crudos = leer_json(ruta_manifiesto)
        datos = proyecto_desde_datos(datos_crudos)
        estado.proyecto = RegistroArchivo(
            estructura.relativa(raiz, ruta_manifiesto), Firma.de(ruta_manifiesto), huella(datos_crudos)
        )

        proyecto = Proyecto(
            nombre=datos.nombre or raiz.name,
            raiz=raiz,
            estandar=datos.estandar,
            idiomas=datos.idiomas,
            indice_capitulos=dict(datos.indice_capitulos),
            taller=Taller(),
        )
        for identificador in datos.ids_usados:
            proyecto.ids.registrar(identificador)

        for bruto in datos.brutos:
            ruta = estructura.ruta_bruto(raiz, bruto)
            bruto.archivo = ruta if ruta.exists() else None
            estado.brutos[bruto.id] = estructura.relativa(raiz, ruta)
            if bruto.archivo is None:
                informe.brutos_faltantes.append(estructura.relativa(raiz, ruta))
            proyecto.taller.brutos[bruto.id] = bruto
            _registrar_id(proyecto, estado, informe, bruto.id, f"Bruto {bruto.nombre}")

        _detectar_brutos_sin_registrar(raiz, estado, informe)
        _cargar_piezas(proyecto, estado, informe)
        _descubrir_capitulos(proyecto, informe)
        proyecto.reconstruir_referencias()
        proyecto.cargador_capitulo = lambda numero: cargar_capitulo(proyecto, estado, numero, informe)
    except Exception:
        if bloqueo is not None:
            bloqueo.liberar()
        raise

    return Apertura(proyecto, estado, informe, bloqueo, solo_lectura)


def _registrar_id(proyecto: Proyecto, estado: EstadoDisco, informe: Informe, identificador: str, que: str) -> str:
    """Registra un ID leído; si ya se vio, devuelve uno nuevo y lo anota en el informe."""
    if identificador in estado.ids_vistos:
        nuevo = proyecto.nuevo_id()
        informe.ids_reasignados.append(f"{que}: {identificador} → {nuevo}")
        estado.ids_vistos.add(nuevo)
        return nuevo
    proyecto.ids.registrar(identificador)
    estado.ids_vistos.add(identificador)
    return identificador


def _cargar_piezas(proyecto: Proyecto, estado: EstadoDisco, informe: Informe) -> None:
    raiz = estado.raiz
    carpeta_taller = raiz / nom.CARPETA_TALLER
    if not carpeta_taller.exists():
        return
    for carpeta in sorted(carpeta_taller.iterdir()):
        manifiesto = carpeta / nom.ARCHIVO_PIEZA
        if not carpeta.is_dir():
            continue
        if not manifiesto.exists():
            informe.taller_sin_receta.append(estructura.relativa(raiz, carpeta))
            continue
        try:
            datos_crudos = leer_json(manifiesto)
            pieza, copias = pieza_desde_datos(datos_crudos)
        except (ValueError, KeyError) as error:
            informe.no_reconocidos.append(f"{estructura.relativa(raiz, manifiesto)} ({error})")
            continue
        ruta_horneado = carpeta / nom.ARCHIVO_HORNEADO
        if ruta_horneado.exists():
            datos_horneado = leer_json(ruta_horneado)
            pieza.horneado = horneado_desde_datos(datos_horneado)
            estado.horneados[pieza.id] = RegistroArchivo(
                estructura.relativa(raiz, ruta_horneado), Firma.de(ruta_horneado), huella(datos_horneado)
            )
        if pieza.horneado is not None:
            ruta = estructura.ruta_horneado(raiz, pieza)
            pieza.horneado.archivo = ruta if ruta is not None and ruta.exists() else None
        else:
            informe.piezas_sin_horneado.append(pieza.nombre)
        proyecto.taller.piezas[pieza.id] = pieza
        _registrar_id(proyecto, estado, informe, pieza.id, f"Pieza {pieza.nombre}")
        estado.piezas[pieza.id] = RegistroArchivo(
            estructura.relativa(raiz, manifiesto), Firma.de(manifiesto), huella(datos_crudos)
        )
        estado.copias_piezas[pieza.id] = copias
        proyecto.referencias.registrar_pieza(pieza.id, pieza.ids_brutos())


def _detectar_brutos_sin_registrar(raiz: Path, estado: EstadoDisco, informe: Informe) -> None:
    conocidos = set(estado.brutos.values())
    for sub in nom.SUBCARPETAS_BRUTOS:
        carpeta = raiz / nom.CARPETA_BRUTOS / sub
        if not carpeta.exists():
            continue
        for ruta in sorted(carpeta.iterdir()):
            if ruta.is_file() and not ruta.name.startswith(".") and estructura.relativa(raiz, ruta) not in conocidos:
                informe.brutos_sin_registrar.append(estructura.relativa(raiz, ruta))


def _descubrir_capitulos(proyecto: Proyecto, informe: Informe) -> None:
    """Capítulos en disco que no están en el índice (por ejemplo, copiados a mano)."""
    assert proyecto.raiz is not None
    for carpeta in sorted(proyecto.raiz.glob("cap[0-9][0-9][0-9][0-9]")):
        try:
            numero = nom.numero_capitulo(carpeta.name)
        except NombreInvalido:
            continue
        if carpeta.is_dir() and numero not in proyecto.indice_capitulos:
            titulo = ""
            manifiesto = carpeta / nom.ARCHIVO_CAPITULO
            if manifiesto.exists():
                try:
                    titulo = str(leer_json(manifiesto).get("titulo", ""))
                except ValueError:
                    pass
            proyecto.indice_capitulos[numero] = titulo
            informe.capitulos_sin_indice.append(carpeta.name)


# --- Cargar un capítulo -----------------------------------------------------------------

def cargar_capitulo(proyecto: Proyecto, estado: EstadoDisco, numero: int, informe: Informe | None = None) -> Capitulo:
    informe = informe if informe is not None else Informe()
    raiz = estado.raiz
    capitulo = Capitulo(numero=numero, titulo=proyecto.indice_capitulos.get(numero, ""))
    estado_cap = estado.capitulo(numero)

    manifiesto = estructura.ruta_manifiesto_capitulo(raiz, numero)
    if manifiesto.exists():
        datos = leer_json(manifiesto)
        aplicar_datos_capitulo(capitulo, datos)
        estado_cap.control[estructura.relativa(raiz, manifiesto)] = RegistroArchivo(
            estructura.relativa(raiz, manifiesto), Firma.de(manifiesto), huella(datos)
        )

    for minuto in capitulo.minutos:
        ruta_minuto = estructura.ruta_manifiesto_minuto(raiz, numero, minuto.numero)
        if ruta_minuto.exists():
            datos = leer_json(ruta_minuto)
            aplicar_datos_minuto(minuto, datos)
            estado_cap.control[estructura.relativa(raiz, ruta_minuto)] = RegistroArchivo(
                estructura.relativa(raiz, ruta_minuto), Firma.de(ruta_minuto), huella(datos)
            )
        ruta_guion = estructura.ruta_guion(raiz, numero, minuto.numero)
        if ruta_guion.exists():
            estado_cap.control[estructura.relativa(raiz, ruta_guion)] = RegistroArchivo(
                estructura.relativa(raiz, ruta_guion),
                Firma.de(ruta_guion),
                huella_texto(ruta_guion.read_text(encoding="utf-8")),
            )
        _cargar_carpeta_elementos(
            proyecto, estado, informe, capitulo, nom.carpeta_minuto(raiz, numero, minuto.numero), en_global=False
        )

    _cargar_carpeta_elementos(proyecto, estado, informe, capitulo, nom.carpeta_global(raiz, numero), en_global=True)
    _cargar_shorts(proyecto, estado, informe, capitulo)

    ruta_renders = estructura.ruta_renders(raiz, numero)
    if ruta_renders.exists():
        datos = leer_json(ruta_renders)
        aplicar_datos_renders(capitulo, datos)
        estado_cap.control[estructura.relativa(raiz, ruta_renders)] = RegistroArchivo(
            estructura.relativa(raiz, ruta_renders), Firma.de(ruta_renders), huella(datos)
        )

    informe.capitulos_cargados.append(numero)
    return capitulo


def _agrupar(carpeta: Path, informe: Informe, raiz: Path) -> dict[str, dict[str, Path]]:
    """Agrupa los archivos de Elementos por nombre base: {'contenido': …, 'gemelo': …}."""
    grupos: dict[str, dict[str, Path]] = {}
    if not carpeta.exists():
        return grupos
    for ruta in sorted(carpeta.iterdir()):
        if ruta.is_dir() or ruta.name.startswith((nom.PREFIJO_CONTROL, ".")):
            continue
        try:
            nombre = NombreElemento.desde_archivo(ruta.name)
        except NombreInvalido:
            informe.no_reconocidos.append(estructura.relativa(raiz, ruta))
            continue
        grupo = grupos.setdefault(nombre.base, {})
        if nombre.es_texto:
            grupo["gemelo"] = ruta
        elif nombre.extension == nom.EXTENSION_GEMELO:
            grupo["gemelo"] = ruta
        else:
            grupo["contenido"] = ruta
    return grupos


def _cargar_carpeta_elementos(
    proyecto: Proyecto,
    estado: EstadoDisco,
    informe: Informe,
    capitulo: Capitulo,
    carpeta: Path,
    en_global: bool,
) -> None:
    raiz = estado.raiz
    estado_cap = estado.capitulo(capitulo.numero)
    for base, grupo in _agrupar(carpeta, informe, raiz).items():
        ruta_gemelo = grupo.get("gemelo")
        ruta_contenido = grupo.get("contenido")
        datos = leer_gemelo(ruta_gemelo) if ruta_gemelo is not None else None

        referencia = ruta_contenido or ruta_gemelo
        assert referencia is not None
        nombre = NombreElemento.desde_archivo(referencia.name)
        if ruta_contenido is None:
            nombre = nombre.con(extension=extension_de_medio(datos, nombre.capa))

        elemento = elemento_desde_datos(datos, nombre, en_global)
        elemento.id = _registrar_id(proyecto, estado, informe, elemento.id, f"{capitulo.codigo}/{base}")

        if ruta_gemelo is None or datos is None:
            informe.gemelos_faltantes.append(estructura.relativa(raiz, referencia))
        if not elemento.es_texto:
            if ruta_contenido is None:
                informe.fuera_de_linea.append(estructura.relativa(raiz, carpeta / nombre.archivo))
            elemento.archivo = ruta_contenido
        if not en_global and carpeta.name != nom.codigo_minuto(elemento.minuto_inicio):
            informe.fuera_de_carpeta.append(estructura.relativa(raiz, referencia))

        _insertar_tolerante(capitulo, elemento, informe)
        informe.elementos += 1
        proyecto.referencias.registrar(elemento, capitulo.numero)

        estado_cap.elementos[elemento.id] = RegistroElemento(
            contenido=None if ruta_contenido is None else estructura.relativa(raiz, ruta_contenido),
            gemelo=estructura.relativa(raiz, ruta_gemelo) if ruta_gemelo is not None
            else estructura.relativa(raiz, carpeta / nombre.gemelo),
            firma_contenido=None if ruta_contenido is None else Firma.de(ruta_contenido),
            firma_gemelo=None if ruta_gemelo is None else Firma.de(ruta_gemelo),
            huella_gemelo="" if datos is None else huella(datos),
            ref_fuente=elemento.fuente.ref,
            version_fuente=elemento.fuente.version,
            extension=elemento.extension,
        )


def _insertar_tolerante(capitulo: Capitulo, elemento: Elemento, informe: Informe) -> None:
    """Inserta sin rechazar: lo que está en disco no se pierde aunque rompa una regla."""
    contenedor = capitulo.contenedor_de(elemento)
    candidatos = capitulo.global_ if elemento.en_global else capitulo.elementos_de_minutos()
    conflicto = buscar_solape(elemento, candidatos)
    if conflicto is not None:
        informe.solapes.append(
            f"{capitulo.codigo} {elemento.capa.codigo}: {elemento.id} con {conflicto.id}"
        )
    contenedor.elementos[elemento.id] = elemento


def _cargar_shorts(proyecto: Proyecto, estado: EstadoDisco, informe: Informe, capitulo: Capitulo) -> None:
    raiz = estado.raiz
    carpeta = nom.carpeta_shorts(raiz, capitulo.numero)
    if not carpeta.exists():
        return
    estado_cap = estado.capitulo(capitulo.numero)
    for ruta in sorted(carpeta.iterdir()):
        if ruta.is_dir() or ruta.name.startswith((nom.PREFIJO_CONTROL, ".")):
            continue
        try:
            nombre, version = NombreShort.desde_archivo(ruta.name)
        except NombreInvalido:
            informe.no_reconocidos.append(estructura.relativa(raiz, ruta))
            continue
        if version is not None:
            continue  # render de un Short: se conserva tal cual
        datos = leer_gemelo(ruta)
        try:
            short = short_desde_datos(datos, nombre)
        except ValueError as error:
            informe.no_reconocidos.append(f"{estructura.relativa(raiz, ruta)} ({error})")
            continue
        short.id = _registrar_id(proyecto, estado, informe, short.id, f"{capitulo.codigo}/shorts/{nombre.base}")
        capitulo.shorts[short.id] = short
        informe.shorts += 1
        estado_cap.shorts[short.id] = RegistroArchivo(
            estructura.relativa(raiz, ruta), Firma.de(ruta), "" if datos is None else huella(datos)
        )
