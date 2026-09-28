# Editor de video por capítulos y minutos

Editor de video de escritorio en Python para Linux. Organiza todo por tiempo:
capítulos de exactamente 24 minutos, una carpeta por minuto y nombres de
archivo que dicen en qué instante aparece cada elemento.

La arquitectura completa, las decisiones y las épicas están en
**[PROJECT.md](PROJECT.md)**, que es la referencia única del proyecto.

## Estado

| Fase | Épicas | Estado |
|---|---|---|
| A — Fundamentos | E0 fundación · E1 base transversal · E2 tiempo y nomenclatura · E3 espacio · E4 modelo | ✅ Código escrito y auditado (revisión 4) |
| B — Persistencia y edición | E5 disco · E6 comandos | Pendiente |
| C — Motor y servicios | E7–E11 | Pendiente |
| D — Interfaz | E12–E16 | Pendiente |
| E — Capacidades creativas | E17–E20 | Pendiente |
| F — Cierre | E21–E22 | Pendiente |

## Requisitos

- Linux (Debian/Ubuntu como referencia).
- Python 3.13 recomendado (mínimo 3.12).
- Dependencias de sistema para la interfaz y el video: ver PROJECT.md, sección 15.4.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

En PyCharm: crear el intérprete desde `.venv/` y una configuración de ejecución
con el script `main.py` y la raíz del repositorio como directorio de trabajo.

## Uso

```bash
python main.py                                    # interfaz (E12)
python main.py RUTA_PROYECTO                      # interfaz con un proyecto (E12)
python main.py --nuevo RUTA_PROYECTO              # crear proyecto (E5)
python main.py --escanear RUTA_PROYECTO           # reconstruir desde el disco (E5)
python main.py --render RUTA --capitulo 1 --minutos 00-05   # render sin interfaz (E10)
python main.py --shorts RUTA --capitulo 1         # Shorts verticales (E20)
```

Mientras un modo no esté implementado, `main.py` indica qué épica lo completa.

## Estructura

```
main.py            punto de entrada único
config/            valores por defecto: estándar, ajustes, distribución, atajos
editor/core/       núcleo en Python puro (sin interfaz)
editor/app/        aplicación Flet
```
