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
| B — Persistencia y edición | E5 disco · E6 comandos | ✅ Código escrito |
| C — Motor y servicios | E7–E11 | ✅ Código escrito y verificado con medios reales |
| D — Interfaz | E12–E16 | ✅ Código escrito y recorrido en Chromium (revisión 8) |
| E — Capacidades creativas | E17–E20 | Pendiente |
| F — Cierre | E21–E22 | Pendiente |

## Requisitos

- Linux (Debian/Ubuntu como referencia).
- Python 3.13 recomendado (mínimo 3.12).
- Dependencias de sistema para la interfaz y el video (libmpv, GTK, `zenity` para el
  selector de archivos, fuentes DejaVu): ver PROJECT.md, sección 15.4.

```bash
sudo apt install libmpv2 libgtk-3-0 libgstreamer1.0-0 zenity fonts-dejavu
```

## Instalación

Guía completa (dependencias del sistema, PyCharm, problemas frecuentes): **[INSTALACION.md](INSTALACION.md)**.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

En PyCharm: crear el intérprete desde `.venv/` y una configuración de ejecución
con el script `main.py` y la raíz del repositorio como directorio de trabajo.

## Uso

```bash
python main.py                                    # interfaz: último proyecto o pantalla de inicio ✅
python main.py RUTA_PROYECTO                      # interfaz con un proyecto ✅
python main.py --nuevo RUTA_PROYECTO              # crear proyecto y abrirlo ✅
python main.py --escanear RUTA_PROYECTO           # revisar el proyecto en disco ✅
python main.py --render RUTA --capitulo 1 --minutos 00-05   # render sin interfaz ✅ (--por-idioma: un archivo por idioma)
python main.py --fotograma RUTA --capitulo 1 --tiempo 02:12.08 --salida f.png  # exportar un fotograma ✅
python main.py --shorts RUTA --capitulo 1         # Shorts verticales (E20)
```

Mientras un modo no esté implementado, `main.py` indica qué épica lo completa.

Flujo básico en la interfaz: importar Brutos (⬆ en el navegador) → en el espacio
**Taller**, marcar entrada y salida, elegir fps y método → **Crear Pieza** →
**Hornear** → **Colocar en el cabezal** → editar en **Minuto** (timeline, monitor,
inspector) → Ctrl+S → **Render**. Gestos y atajos: PROJECT.md, sección 16.6.

## Estructura

```
main.py            punto de entrada único
config/            valores por defecto: estándar, ajustes, distribución, atajos
editor/core/       núcleo en Python puro (sin interfaz)
editor/app/        aplicación Flet
```
