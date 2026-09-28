"""`_guion.txt`: reflejo legible de un minuto (T5.10).

Se genera al guardar y nunca se lee: sirve para revisar el minuto con el
programa cerrado (PROJECT.md, 8.7).
"""

from __future__ import annotations

from editor.core.modelo.capa import TipoCapa
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.elemento import Elemento
from editor.core.tiempo.granularidad import Duracion, Instante

LINEA = "─" * 72


def _posicion(elemento: Elemento) -> str:
    if elemento.capa.tipo is TipoCapa.AUDIO:
        return "—"
    def extremos(eje: str, base: float) -> tuple[float, float]:
        pista = elemento.animacion.pistas.get(eje)
        if pista is None or pista.vacia:
            return base, base
        return pista.keyframes[0].valor, pista.keyframes[-1].valor

    x0, x1 = extremos("x", elemento.espacio.x)
    y0, y1 = extremos("y", elemento.espacio.y)
    if (x0, y0) == (x1, y1):
        return f"pos ({x0:g},{y0:g})"
    return f"pos ({x0:g},{y0:g})→({x1:g},{y1:g})"


def _detalle(elemento: Elemento) -> str:
    if elemento.capa.tipo is TipoCapa.AUDIO:
        return f"vol {round(elemento.audio.volumen * 100)} %" + (" silenciado" if elemento.audio.silenciado else "")
    if elemento.es_texto and elemento.texto is not None:
        return f"«{elemento.texto.texto[:30]}»"
    escala = elemento.espacio.escala_x
    partes = [f"esc {escala:.2f}"]
    if elemento.espacio.opacidad < 1:
        partes.append(f"opac {round(elemento.espacio.opacidad * 100)} %")
    if elemento.tiempo.congelado:
        partes.append("congelado")
    if elemento.tiempo.velocidad != 1:
        partes.append(f"vel {elemento.tiempo.velocidad:g}×")
    if elemento.transicion_entrada is not None:
        partes.append(f"transición {elemento.transicion_entrada.tipo}")
    return "  ".join(partes)


def generar(capitulo: Capitulo, numero_minuto: int, fps: int = 24) -> str:
    minuto = capitulo.minuto(numero_minuto)
    cabecera = f"MINUTO {numero_minuto:02d} · {capitulo.codigo}"
    if capitulo.titulo:
        cabecera += f" · {capitulo.titulo}"
    lineas = [f"{cabecera} · lienzo 1280×720 · {fps} fps", LINEA]

    desbordes = capitulo.desbordes_hacia(numero_minuto)
    for elemento in sorted(desbordes, key=lambda e: (e.inicio, e.capa.codigo)):
        lineas.append(
            f"  (entra desde min{elemento.minuto_inicio:02d})  {elemento.capa.codigo:<3} {elemento.nombre}"
        )

    for elemento in sorted(minuto, key=lambda e: (e.inicio, e.capa.tipo.value, e.capa.numero)):
        lineas.append(
            f"{Instante(elemento.inicio).timecode()}  {elemento.capa.codigo:<3} {elemento.nombre:<24} "
            f"{Duracion(elemento.duracion).legible():>8}  {_posicion(elemento):<28} {_detalle(elemento)}".rstrip()
        )
    if minuto.vacia and not desbordes:
        lineas.append("(vacío)")
    if minuto.notas:
        lineas += [LINEA, "Notas:", minuto.notas]
    return "\n".join(lineas) + "\n"
