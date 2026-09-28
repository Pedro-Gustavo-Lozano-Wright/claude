"""Estado automático: lo que producen los servicios, escrito en el momento.

Separado de lo que edita el usuario (PROJECT.md, 22.7):

| Archivo | Contenido | Lo escribe |
|---|---|---|
| `capNNNN/render/_renders.json` | Entregables, último render de cada minuto y de cada Short | Servicio de render (E10, E20) |
| `taller/pieNNNN…/_horneado.json` | Resultado del último horneado | Servicio de horneado (E9) |

Así un render o un horneado nunca se pierde por cerrar sin guardar, y
escribirlo nunca persiste ediciones que el usuario no guardó. Cada escritura
actualiza el estado conocido del disco para que el siguiente guardado no la
confunda con un cambio externo.
"""

from __future__ import annotations

from editor.core.modelo.capitulo import Capitulo
from editor.core.modelo.pieza import Pieza
from editor.core.modelo.proyecto import Proyecto
from editor.core.proyecto_fs import estructura
from editor.core.proyecto_fs.estado_disco import EstadoDisco, Firma, RegistroArchivo
from editor.core.proyecto_fs.manifiestos import horneado_a_datos, renders_a_datos
from editor.core.proyecto_fs.serializacion import escribir_json_atomico, huella


def guardar_renders(proyecto: Proyecto, estado: EstadoDisco, capitulo: Capitulo) -> None:
    assert proyecto.raiz is not None
    ruta = estructura.ruta_renders(proyecto.raiz, capitulo.numero)
    datos = renders_a_datos(capitulo)
    escribir_json_atomico(ruta, datos)
    relativa = estructura.relativa(proyecto.raiz, ruta)
    estado.capitulo(capitulo.numero).control[relativa] = RegistroArchivo(relativa, Firma.de(ruta), huella(datos))


def guardar_horneado(proyecto: Proyecto, estado: EstadoDisco, pieza: Pieza) -> None:
    assert proyecto.raiz is not None
    ruta = estructura.ruta_manifiesto_horneado(proyecto.raiz, pieza)
    datos = horneado_a_datos(pieza.horneado)
    escribir_json_atomico(ruta, datos)
    estado.horneados[pieza.id] = RegistroArchivo(estructura.relativa(proyecto.raiz, ruta), Firma.de(ruta), huella(datos))
