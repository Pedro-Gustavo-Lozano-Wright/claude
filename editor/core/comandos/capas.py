"""Estado de capas, marcadores, título del capítulo y estado de los minutos (T6.7)."""

from __future__ import annotations

from dataclasses import replace

from editor.core.comandos.comando import Afectados, EdicionRechazada
from editor.core.comandos.estado_capitulo import EdicionEstadoCapitulo
from editor.core.estandar import FOTOGRAMAS_POR_CAPITULO, MINUTOS_POR_CAPITULO
from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.marcador import EstadoCapa, Marcador
from editor.core.tiempo import granularidad

TODOS_LOS_MINUTOS = set(range(MINUTOS_POR_CAPITULO))


class CambiarEstadoCapa(EdicionEstadoCapitulo):
    """Visible, silenciada, bloqueada, solo o idioma de una capa ("V1", "A2", "GA1"…)."""

    descripcion = "Cambiar capa"
    partes = ("capas",)

    def __init__(self, capitulo: int, clave: str, **cambios: object) -> None:
        super().__init__(capitulo)
        validos = {"visible", "silenciada", "bloqueada", "solo", "idioma"}
        desconocidos = set(cambios) - validos
        if desconocidos:
            raise ValueError(f"Propiedades de capa desconocidas: {', '.join(sorted(desconocidos))}")
        self.clave = clave
        self.cambios = cambios

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        actual = capitulo.capas.get(self.clave, EstadoCapa())
        capitulo.capas[self.clave] = replace(actual, **self.cambios)  # type: ignore[arg-type]
        # Solo "bloqueada" no cambia lo que se ve o se oye.
        minutos = set() if set(self.cambios) == {"bloqueada"} else TODOS_LOS_MINUTOS
        return Afectados(self.capitulo, minutos=minutos, estado_capitulo=True)


class PonerMarcador(EdicionEstadoCapitulo):
    descripcion = "Poner marcador"
    partes = ("marcadores",)

    def __init__(self, capitulo: int, marcador: Marcador) -> None:
        super().__init__(capitulo)
        if marcador.f >= FOTOGRAMAS_POR_CAPITULO:
            raise ValueError("El marcador cae fuera del capítulo.")
        self.marcador = marcador

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        capitulo.marcadores = [m for m in capitulo.marcadores if m.f != self.marcador.f] + [replace(self.marcador)]
        capitulo.marcadores.sort(key=lambda m: m.f)
        return Afectados(self.capitulo, estado_capitulo=True)


class QuitarMarcador(EdicionEstadoCapitulo):
    descripcion = "Quitar marcador"
    partes = ("marcadores",)

    def __init__(self, capitulo: int, f: int) -> None:
        super().__init__(capitulo)
        self.f = f

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        restantes = [m for m in capitulo.marcadores if m.f != self.f]
        if len(restantes) == len(capitulo.marcadores):
            raise EdicionRechazada(f"No hay marcador en el fotograma {self.f}.")
        capitulo.marcadores = restantes
        return Afectados(self.capitulo, estado_capitulo=True)


class MoverMarcador(EdicionEstadoCapitulo):
    descripcion = "Mover marcador"
    partes = ("marcadores",)

    def __init__(self, capitulo: int, f_origen: int, f_destino: int) -> None:
        super().__init__(capitulo)
        if not granularidad.dentro_del_capitulo(f_destino):
            raise ValueError("El marcador cae fuera del capítulo.")
        self.f_origen = f_origen
        self.f_destino = f_destino

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        marcador = next((m for m in capitulo.marcadores if m.f == self.f_origen), None)
        if marcador is None:
            raise EdicionRechazada(f"No hay marcador en el fotograma {self.f_origen}.")
        capitulo.marcadores = [m for m in capitulo.marcadores if m.f not in (self.f_origen, self.f_destino)]
        capitulo.marcadores.append(replace(marcador, f=self.f_destino))
        capitulo.marcadores.sort(key=lambda m: m.f)
        return Afectados(self.capitulo, estado_capitulo=True)


class CambiarTituloCapitulo(EdicionEstadoCapitulo):
    descripcion = "Cambiar título"
    partes = ("titulo",)

    def __init__(self, capitulo: int, titulo: str) -> None:
        super().__init__(capitulo)
        self.titulo = titulo

    def ejecutar(self, proyecto) -> None:  # type: ignore[override]
        self._titulo_indice = proyecto.indice_capitulos.get(self.capitulo, "")
        super().ejecutar(proyecto)
        proyecto.indice_capitulos[self.capitulo] = self.titulo

    def deshacer(self, proyecto) -> None:  # type: ignore[override]
        super().deshacer(proyecto)
        proyecto.indice_capitulos[self.capitulo] = self._titulo_indice

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        capitulo.titulo = self.titulo
        return Afectados(self.capitulo, estado_capitulo=True)


class MarcarMinuto(EdicionEstadoCapitulo):
    """Estado de trabajo manual del minuto (listo) y sus notas (PROJECT.md, 13.3)."""

    descripcion = "Estado del minuto"

    def __init__(self, capitulo: int, minuto: int, listo: bool | None = None, notas: str | None = None) -> None:
        super().__init__(capitulo)
        granularidad.validar_minuto(minuto)
        self.minuto = minuto
        self.listo = listo
        self.notas = notas

    def aplicar(self, capitulo: Capitulo) -> Afectados:
        minuto = capitulo.minuto(self.minuto)
        if self.listo is not None:
            minuto.listo = self.listo
        if self.notas is not None:
            minuto.notas = self.notas
        return Afectados(self.capitulo, estado_capitulo=True)
