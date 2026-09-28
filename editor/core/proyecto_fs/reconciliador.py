"""Reconciliador: hace que el disco refleje el modelo al guardar.

1. **Planificar**: compara el modelo cargado con el último estado conocido del
   disco y decide qué mover, renombrar, copiar, escribir o enviar a la papelera.
   Detecta conflictos (archivos cambiados fuera del programa o destinos
   ocupados) antes de tocar nada.
2. **Ejecutar**: el plan pasa al diario, que lo aplica de forma recuperable.
3. **Refrescar**: el estado conocido se actualiza con lo que quedó en disco.

Orden seguro del plan:
    carpetas → fase A (a temporales y a la papelera) → fase B (temporales a su
    destino) → fase C (renombres dentro de carpetas ya movidas) → copias
    (materialización) → escrituras (gemelos, manifiestos, guiones).

Los renombres pasan siempre por un temporal: así un intercambio A↔B nunca
pisa archivos. Lo que se quita del modelo va a `.papelera/`.

La materialización que exige convertir (extraer el audio de un video,
normalizar una imagen) no se hace aquí: queda en `pendientes` para el
servicio de guardado, que usa el motor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento, TipoFuente
from editor.core.modelo.proyecto import Proyecto
from editor.core.proyecto_fs import estructura, guion
from editor.core.proyecto_fs.diario import CARPETA, COPIAR, MOVER, Diario, Operacion
from editor.core.proyecto_fs.estado_disco import (
    EstadoDisco,
    Firma,
    RegistroArchivo,
    RegistroElemento,
)
from editor.core.proyecto_fs.gemelo import elemento_a_datos, short_a_datos
from editor.core.proyecto_fs.manifiestos import (
    Copia,
    capitulo_a_datos,
    horneado_a_datos,
    minuto_a_datos,
    pieza_a_datos,
    proyecto_a_datos,
    renders_a_datos,
)
from editor.core.proyecto_fs.serializacion import huella, huella_texto, json_legible
from editor.core.tiempo import nomenclatura as nom

registro = logging.getLogger(__name__)


@dataclass(frozen=True)
class Conflicto:
    ruta: str
    motivo: str


@dataclass(frozen=True)
class Materializacion:
    """Copia que requiere el motor: la resuelve el servicio de guardado."""

    capitulo: int
    id_elemento: str
    destino: str
    motivo: str
    origen: str | None = None


@dataclass
class Plan:
    operaciones: list[Operacion] = field(default_factory=list)
    conflictos: list[Conflicto] = field(default_factory=list)
    pendientes: list[Materializacion] = field(default_factory=list)

    @property
    def vacio(self) -> bool:
        return not self.operaciones


@dataclass
class ResultadoGuardado:
    guardado: bool
    operaciones: int = 0
    conflictos: list[Conflicto] = field(default_factory=list)
    pendientes: list[Materializacion] = field(default_factory=list)
    # Pasos del diario que no se pudieron completar (el resto sí se aplicó).
    errores: list[str] = field(default_factory=list)


class SoloLectura(PermissionError):
    pass


class _Constructor:
    """Acumula las operaciones de un plan por fases."""

    def __init__(self, proyecto: Proyecto, estado: EstadoDisco, diario: Diario) -> None:
        assert proyecto.raiz is not None
        self.proyecto = proyecto
        self.estado = estado
        self.diario = diario
        self.raiz = proyecto.raiz
        self.carpetas: list[Operacion] = []
        self.fase_a: list[Operacion] = []
        self.fase_b: list[Operacion] = []
        self.fase_c: list[Operacion] = []
        self.copias: list[Operacion] = []
        self.escrituras: list[Operacion] = []
        self.conflictos: list[Conflicto] = []
        self.pendientes: list[Materializacion] = []
        self.liberados: set[str] = set()
        self.destinos: dict[str, set[str]] = {}   # destino → rutas propias que pueden ocuparlo
        self.papelera = f"{nom.CARPETA_PAPELERA}/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self._contador = 0

    # --- Primitivas --------------------------------------------------------------

    def _siguiente(self) -> str:
        self._contador += 1
        return f"{self._contador:06d}"

    def rel(self, ruta: Path) -> str:
        return estructura.relativa(self.raiz, ruta)

    def existe(self, relativa: str | None) -> bool:
        return relativa is not None and (self.raiz / relativa).exists()

    def verificar(self, relativa: str | None, firma: Firma | None) -> None:
        """Conflicto si el archivo cambió fuera del programa desde que se leyó."""
        if relativa is None or firma is None:
            return
        actual = self.estado.firma(relativa)
        if actual is not None and actual != firma:
            self.conflictos.append(Conflicto(relativa, "modificado fuera del programa"))

    def carpeta(self, ruta: Path) -> None:
        if not ruta.is_dir():
            self.carpetas.append(Operacion(CARPETA, self.rel(ruta)))

    def mover(self, origen: str, destino: str) -> None:
        if origen == destino:
            self.reservar(destino, {origen})
            return
        temporal = self.diario.ruta_temporal(self._siguiente())
        self.fase_a.append(Operacion(MOVER, temporal, origen))
        self.fase_b.append(Operacion(MOVER, destino, temporal))
        self.liberados.add(origen)
        self.reservar(destino, set())

    def a_papelera(self, relativa: str) -> None:
        self.fase_a.append(Operacion(MOVER, f"{self.papelera}/{relativa}", relativa))
        self.liberados.add(relativa)

    def copiar(self, origen: str, destino: str) -> None:
        self.copias.append(Operacion(COPIAR, destino, origen))
        self.reservar(destino, set())

    def escribir(self, destino: str, texto: str, propias: set[str] | None = None) -> None:
        preparado = self.diario.preparar_texto(self._siguiente(), texto)
        self.escrituras.append(Operacion(MOVER, destino, preparado))
        self.reservar(destino, propias or {destino})

    def reservar(self, destino: str, propias: set[str]) -> None:
        self.destinos.setdefault(destino, set()).update(propias)

    def comprobar_destinos(self) -> None:
        """Un destino ocupado por un archivo ajeno que no se libera es un conflicto."""
        for destino, propias in self.destinos.items():
            if destino in propias or destino in self.liberados:
                continue
            if self.existe(destino):
                self.conflictos.append(Conflicto(destino, "el destino ya existe y no pertenece a este elemento"))

    def plan(self) -> Plan:
        self.comprobar_destinos()
        operaciones = self.carpetas + self.fase_a + self.fase_b + self.fase_c + self.copias + self.escrituras
        return Plan(operaciones, self.conflictos, self.pendientes)


# --- Planificación ----------------------------------------------------------------------

def planificar(proyecto: Proyecto, estado: EstadoDisco, diario: Diario) -> Plan:
    if proyecto.raiz is None:
        raise ValueError("El proyecto no tiene carpeta.")
    c = _Constructor(proyecto, estado, diario)

    # Registros de Elementos que ya no están en su capítulo: pueden haberse
    # movido a otro capítulo cargado (se mueven) o haberse quitado (papelera).
    huerfanos: dict[str, tuple[int, RegistroElemento]] = {}
    for numero, capitulo in proyecto.capitulos.items():
        presentes = {e.id for e in capitulo.todos_los_elementos()}
        for identificador, registro_elemento in estado.capitulo(numero).elementos.items():
            if identificador not in presentes:
                huerfanos[identificador] = (numero, registro_elemento)

    for capitulo in proyecto.capitulos_cargados():
        _planificar_capitulo(c, capitulo, huerfanos)

    for _, registro_elemento in huerfanos.values():
        for relativa, firma in (
            (registro_elemento.contenido, registro_elemento.firma_contenido),
            (registro_elemento.gemelo, registro_elemento.firma_gemelo),
        ):
            if c.existe(relativa):
                c.verificar(relativa, firma)
                c.a_papelera(relativa)  # type: ignore[arg-type]

    _planificar_taller(c)
    _planificar_proyecto(c)
    return c.plan()


def _planificar_capitulo(c: _Constructor, capitulo: Capitulo, huerfanos: dict[str, tuple[int, RegistroElemento]]) -> None:
    raiz = c.raiz
    numero = capitulo.numero
    estado_cap = c.estado.capitulo(numero)

    for minuto in range(len(capitulo.minutos)):
        c.carpeta(nom.carpeta_minuto(raiz, numero, minuto))
    for carpeta in (nom.carpeta_global, nom.carpeta_render, nom.carpeta_shorts):
        c.carpeta(carpeta(raiz, numero))

    for elemento in capitulo.todos_los_elementos():
        registro_elemento = estado_cap.elementos.get(elemento.id)
        if registro_elemento is None and elemento.id in huerfanos:
            registro_elemento = huerfanos.pop(elemento.id)[1]
        _planificar_elemento(c, numero, elemento, registro_elemento)

    _planificar_control(c, estructura.ruta_manifiesto_capitulo(raiz, numero), capitulo_a_datos(capitulo), estado_cap.control)
    _planificar_control(c, estructura.ruta_renders(raiz, numero), renders_a_datos(capitulo), estado_cap.control)
    for minuto in capitulo.minutos:
        _planificar_control(
            c, estructura.ruta_manifiesto_minuto(raiz, numero, minuto.numero), minuto_a_datos(minuto), estado_cap.control
        )
        texto = guion.generar(capitulo, minuto.numero, c.proyecto.estandar.fps)
        ruta_guion = c.rel(estructura.ruta_guion(raiz, numero, minuto.numero))
        conocido = estado_cap.control.get(ruta_guion)
        if conocido is None or conocido.huella != huella_texto(texto):
            if conocido is not None:
                c.verificar(ruta_guion, conocido.firma)
            c.escribir(ruta_guion, texto)

    presentes = set(capitulo.shorts)
    for identificador, conocido in estado_cap.shorts.items():
        if identificador not in presentes and c.existe(conocido.ruta):
            c.verificar(conocido.ruta, conocido.firma)
            c.a_papelera(conocido.ruta)
    for short in capitulo.shorts.values():
        destino = c.rel(estructura.ruta_receta_short(raiz, numero, short))
        datos = short_a_datos(short)
        conocido = estado_cap.shorts.get(short.id)
        if conocido is not None and c.existe(conocido.ruta):
            c.verificar(conocido.ruta, conocido.firma)
            if conocido.huella == huella(datos):
                c.mover(conocido.ruta, destino)
                continue
            if conocido.ruta != destino:
                c.a_papelera(conocido.ruta)
        c.escribir(destino, json_legible(datos), {destino} | ({conocido.ruta} if conocido else set()))


def _planificar_elemento(c: _Constructor, capitulo: int, elemento: Elemento, conocido: RegistroElemento | None) -> None:
    raiz = c.raiz
    destino_gemelo = c.rel(estructura.ruta_gemelo(raiz, capitulo, elemento))
    datos = elemento_a_datos(elemento)

    if not elemento.es_texto:
        ruta_contenido = estructura.ruta_contenido(raiz, capitulo, elemento)
        assert ruta_contenido is not None
        destino = c.rel(ruta_contenido)
        vigente = (
            conocido is not None
            and conocido.contenido is not None
            and c.existe(conocido.contenido)
            and conocido.ref_fuente == elemento.fuente.ref
            and conocido.version_fuente == elemento.fuente.version
            and conocido.extension == elemento.extension
        )
        if vigente:
            assert conocido is not None and conocido.contenido is not None
            c.verificar(conocido.contenido, conocido.firma_contenido)
            c.mover(conocido.contenido, destino)
        else:
            if conocido is not None and c.existe(conocido.contenido):
                c.verificar(conocido.contenido, conocido.firma_contenido)
                c.a_papelera(conocido.contenido)  # type: ignore[arg-type]
            _planificar_materializacion(c, capitulo, elemento, destino)

    propias = {destino_gemelo}
    if conocido is not None and c.existe(conocido.gemelo):
        c.verificar(conocido.gemelo, conocido.firma_gemelo)
        propias.add(conocido.gemelo)
        if conocido.huella_gemelo == huella(datos):
            c.mover(conocido.gemelo, destino_gemelo)
            return
        if conocido.gemelo != destino_gemelo:
            c.a_papelera(conocido.gemelo)
    c.escribir(destino_gemelo, json_legible(datos), propias)


def _planificar_materializacion(c: _Constructor, capitulo: int, elemento: Elemento, destino: str) -> None:
    """Copia el archivo de la fuente al minuto; si hace falta convertir, queda pendiente."""
    taller = c.proyecto.taller
    origen: Path | None = None
    extension_origen = ""
    if elemento.fuente.tipo is TipoFuente.PIEZA:
        pieza = taller.piezas.get(elemento.fuente.ref)
        if pieza is not None and pieza.horneado is not None and pieza.horneado.archivo is not None:
            # Ruta que tendrá tras este guardado: la carpeta de la Pieza puede moverse
            # en el mismo plan (renombre), y las copias se hacen después de los movimientos.
            origen = estructura.ruta_horneado(c.raiz, pieza)
            extension_origen = pieza.horneado.extension
    elif elemento.fuente.tipo is TipoFuente.BRUTO:
        bruto = taller.brutos.get(elemento.fuente.ref)
        if bruto is not None and bruto.archivo is not None:
            origen = bruto.archivo
            extension_origen = bruto.extension

    if origen is None:
        recuperado = _buscar_en_papelera(c.raiz, elemento)
        if recuperado is not None:
            c.copiar(c.rel(recuperado), destino)
            return
        c.pendientes.append(Materializacion(capitulo, elemento.id, destino, "fuente no disponible"))
        return
    if extension_origen != elemento.extension:
        motivo = "extraer audio" if elemento.capa.codigo.startswith("A") else "convertir formato"
        c.pendientes.append(Materializacion(capitulo, elemento.id, destino, motivo, c.rel(origen)))
        return
    c.copiar(c.rel(origen), destino)


def _buscar_en_papelera(raiz: Path, elemento: Elemento) -> Path | None:
    """Último archivo de medios de este Elemento enviado a la papelera (deshacer tras guardar)."""
    carpeta = raiz / nom.CARPETA_PAPELERA
    if not carpeta.exists():
        return None
    candidatos = sorted(carpeta.rglob(f"*__{elemento.id}.{elemento.extension}"), reverse=True)
    return candidatos[0] if candidatos else None


def _planificar_control(c: _Constructor, ruta: Path, datos: dict, conocidos: dict[str, RegistroArchivo]) -> None:
    relativa = c.rel(ruta)
    conocido = conocidos.get(relativa)
    if conocido is not None and conocido.huella == huella(datos):
        return
    if conocido is not None:
        c.verificar(relativa, conocido.firma)
    c.escribir(relativa, json_legible(datos))


def _planificar_taller(c: _Constructor) -> None:
    raiz = c.raiz
    taller = c.proyecto.taller
    for identificador, conocido in c.estado.piezas.items():
        if identificador not in taller.piezas:
            carpeta = str(Path(conocido.ruta).parent.as_posix())
            if c.existe(carpeta):
                c.a_papelera(carpeta)
    for pieza in taller.piezas.values():
        carpeta_nueva = c.rel(estructura.carpeta_pieza(raiz, pieza))
        conocido = c.estado.piezas.get(pieza.id)
        carpeta_vieja = _carpeta_actual_de_pieza(c, pieza)
        movida = False
        if carpeta_vieja is not None and carpeta_vieja != carpeta_nueva and c.existe(carpeta_vieja):
            c.mover(carpeta_vieja, carpeta_nueva)
            movida = True
            if pieza.horneado is not None:
                nombre_viejo = f"{Path(carpeta_vieja).name}.{pieza.horneado.extension}"
                nombre_nuevo = pieza.nombre_archivo().archivo(pieza.horneado.extension)
                c.fase_c.append(Operacion(MOVER, f"{carpeta_nueva}/{nombre_nuevo}", f"{carpeta_nueva}/{nombre_viejo}"))
        elif carpeta_vieja is None:
            c.carpeta(raiz / carpeta_nueva)
        datos = pieza_a_datos(pieza, _copias_actuales(c.proyecto, c.estado, pieza.id))
        destino = f"{carpeta_nueva}/{nom.ARCHIVO_PIEZA}"
        if conocido is None or conocido.huella != huella(datos) or carpeta_nueva != Path(conocido.ruta).parent.as_posix():
            if conocido is not None:
                c.verificar(conocido.ruta, conocido.firma)
            c.escribir(destino, json_legible(datos), {destino, conocido.ruta} if conocido else {destino})

        datos_horneado = horneado_a_datos(pieza.horneado)
        destino_horneado = f"{carpeta_nueva}/{nom.ARCHIVO_HORNEADO}"
        conocido_horneado = c.estado.horneados.get(pieza.id)
        en_su_lugar = conocido_horneado is not None and (
            movida or Path(conocido_horneado.ruta).parent.as_posix() == carpeta_nueva
        )
        if not en_su_lugar or conocido_horneado is None or conocido_horneado.huella != huella(datos_horneado):
            if conocido_horneado is not None:
                c.verificar(conocido_horneado.ruta, conocido_horneado.firma)
            propias = {destino_horneado} | ({conocido_horneado.ruta} if conocido_horneado else set())
            c.escribir(destino_horneado, json_legible(datos_horneado), propias)

    for identificador, relativa in c.estado.brutos.items():
        if identificador not in taller.brutos and c.existe(relativa):
            c.a_papelera(relativa)


def _carpeta_actual_de_pieza(c: _Constructor, pieza) -> str | None:
    """Dónde está hoy la carpeta de la Pieza en disco (puede tener su nombre anterior).

    Se busca por la receta guardada, por el `_horneado.json` escrito por el servicio
    o por el archivo horneado: una Pieza horneada y renombrada antes del primer
    guardado solo se conoce por estos dos últimos.
    """
    candidatos = []
    if pieza.id in c.estado.piezas:
        candidatos.append(Path(c.estado.piezas[pieza.id].ruta).parent.as_posix())
    if pieza.id in c.estado.horneados:
        candidatos.append(Path(c.estado.horneados[pieza.id].ruta).parent.as_posix())
    if pieza.horneado is not None and pieza.horneado.archivo is not None:
        try:
            candidatos.append(c.rel(pieza.horneado.archivo.parent))
        except ValueError:
            pass
    for candidato in candidatos:
        if c.existe(candidato):
            return candidato
    return None


def _planificar_proyecto(c: _Constructor) -> None:
    datos = proyecto_a_datos(c.proyecto)
    relativa = c.rel(estructura.ruta_manifiesto_proyecto(c.raiz))
    conocido = c.estado.proyecto
    if conocido is not None and conocido.huella == huella(datos):
        return
    if conocido is not None:
        c.verificar(relativa, conocido.firma)
    c.escribir(relativa, json_legible(datos))


# --- Guardar y refrescar ---------------------------------------------------------------------

def guardar(proyecto: Proyecto, estado: EstadoDisco, solo_lectura: bool = False, forzar: bool = False) -> ResultadoGuardado:
    """Planifica y ejecuta. Con conflictos no toca nada, salvo que `forzar` sea True."""
    if solo_lectura:
        raise SoloLectura("El proyecto está abierto en solo lectura.")
    assert proyecto.raiz is not None
    diario = Diario(proyecto.raiz)
    diario.limpiar_restos()
    plan = planificar(proyecto, estado, diario)
    if plan.conflictos and not forzar:
        diario.limpiar_restos()
        return ResultadoGuardado(False, 0, plan.conflictos, plan.pendientes)
    errores = diario.ejecutar(plan.operaciones) if plan.operaciones else []
    refrescar_estado(proyecto, estado)
    registro.info(
        "Proyecto guardado: %d operaciones, %d pendientes, %d errores.",
        len(plan.operaciones), len(plan.pendientes), len(errores),
    )
    return ResultadoGuardado(True, len(plan.operaciones), plan.conflictos, plan.pendientes, errores)


def registrar_manifiesto_proyecto(proyecto: Proyecto, estado: EstadoDisco) -> None:
    """Tras escribir `_proyecto.json` fuera de un guardado (p. ej. al crear un capítulo):
    lo escrito por el programa no debe verse después como "modificado fuera del programa"."""
    assert proyecto.raiz is not None
    ruta = estructura.ruta_manifiesto_proyecto(proyecto.raiz)
    estado.proyecto = RegistroArchivo(estructura.relativa(proyecto.raiz, ruta), Firma.de(ruta),
                                      huella(proyecto_a_datos(proyecto)))


def refrescar_estado(proyecto: Proyecto, estado: EstadoDisco) -> None:
    """Deja el estado conocido igual a lo que hay en disco para lo cargado en memoria."""
    assert proyecto.raiz is not None
    raiz = proyecto.raiz

    def registro_archivo(ruta: Path, marca: str) -> RegistroArchivo:
        return RegistroArchivo(estructura.relativa(raiz, ruta), Firma.de(ruta), marca)

    for capitulo in proyecto.capitulos_cargados():
        numero = capitulo.numero
        estado_cap = estado.capitulo(numero)
        estado_cap.elementos.clear()
        for elemento in capitulo.todos_los_elementos():
            ruta_contenido = estructura.ruta_contenido(raiz, numero, elemento)
            ruta_gemelo = estructura.ruta_gemelo(raiz, numero, elemento)
            materializado = ruta_contenido is not None and ruta_contenido.exists()
            if ruta_contenido is not None:
                elemento.archivo = ruta_contenido if materializado else None
            estado_cap.elementos[elemento.id] = RegistroElemento(
                contenido=estructura.relativa(raiz, ruta_contenido) if materializado and ruta_contenido else None,
                gemelo=estructura.relativa(raiz, ruta_gemelo),
                firma_contenido=Firma.de(ruta_contenido) if materializado and ruta_contenido else None,
                firma_gemelo=Firma.de(ruta_gemelo),
                huella_gemelo=huella(elemento_a_datos(elemento)) if ruta_gemelo.exists() else "",
                ref_fuente=elemento.fuente.ref,
                version_fuente=elemento.fuente.version,
                extension=elemento.extension,
            )
        estado_cap.control.clear()
        ruta = estructura.ruta_manifiesto_capitulo(raiz, numero)
        estado_cap.control[estructura.relativa(raiz, ruta)] = registro_archivo(ruta, huella(capitulo_a_datos(capitulo)))
        ruta = estructura.ruta_renders(raiz, numero)
        estado_cap.control[estructura.relativa(raiz, ruta)] = registro_archivo(ruta, huella(renders_a_datos(capitulo)))
        for minuto in capitulo.minutos:
            ruta = estructura.ruta_manifiesto_minuto(raiz, numero, minuto.numero)
            estado_cap.control[estructura.relativa(raiz, ruta)] = registro_archivo(ruta, huella(minuto_a_datos(minuto)))
            ruta = estructura.ruta_guion(raiz, numero, minuto.numero)
            texto = guion.generar(capitulo, minuto.numero, proyecto.estandar.fps)
            estado_cap.control[estructura.relativa(raiz, ruta)] = registro_archivo(ruta, huella_texto(texto))
        estado_cap.shorts = {
            short.id: registro_archivo(estructura.ruta_receta_short(raiz, numero, short), huella(short_a_datos(short)))
            for short in capitulo.shorts.values()
        }

    estado.piezas.clear()
    estado.horneados.clear()
    for pieza in proyecto.taller.piezas.values():
        copias = _copias_actuales(proyecto, estado, pieza.id)
        estado.copias_piezas[pieza.id] = copias
        estado.piezas[pieza.id] = registro_archivo(
            estructura.ruta_manifiesto_pieza(raiz, pieza), huella(pieza_a_datos(pieza, copias))
        )
        estado.horneados[pieza.id] = registro_archivo(
            estructura.ruta_manifiesto_horneado(raiz, pieza), huella(horneado_a_datos(pieza.horneado))
        )
        if pieza.horneado is not None:
            ruta = estructura.ruta_horneado(raiz, pieza)
            pieza.horneado.archivo = ruta if ruta is not None and ruta.exists() else None
    for identificador in [i for i in estado.copias_piezas if i not in proyecto.taller.piezas]:
        del estado.copias_piezas[identificador]

    estado.brutos = {b.id: estructura.relativa(raiz, estructura.ruta_bruto(raiz, b)) for b in proyecto.taller.brutos.values()}
    estado.proyecto = registro_archivo(estructura.ruta_manifiesto_proyecto(raiz), huella(proyecto_a_datos(proyecto)))


def _copias_actuales(proyecto: Proyecto, estado: EstadoDisco, id_pieza: str) -> list[Copia]:
    cargados = set(proyecto.capitulos)
    anteriores = [c for c in estado.copias_piezas.get(id_pieza, []) if c.capitulo not in cargados]
    actuales = []
    for id_elemento in proyecto.referencias.elementos_de_fuente(id_pieza):
        ubicacion = proyecto.referencias.ubicacion(id_elemento)
        if ubicacion is not None and ubicacion.capitulo in cargados:
            actuales.append(Copia(ubicacion.capitulo, ubicacion.minuto, id_elemento))
    return anteriores + actuales
