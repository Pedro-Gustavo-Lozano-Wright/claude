# Video Editor

Scaffolding para un editor de video no lineal (NLE) de escritorio en Python.

> **Estado: andamiaje sin implementar.** Todos los módulos `.py` están vacíos
> (0 bytes). Este repositorio publica la *estructura* y el *diseño* de dos
> arquitecturas alternativas, no código funcional. No hay nada que importar ni
> que ejecutar todavía.

## Arquitectura

El proyecto contiene dos borradores paralelos del mismo editor. Son mutually
exclusive: no forman un sistema único, son el resultado de explorar dos
enfoques distintos.

### `deep_video_editor/` — NLE de escritorio, UI plana

- `app/ui/` — un único nivel de módulos de UI: `timeline`, `viewer`,
  `effects_panel`, `inspector`, `graph_editor` (grafo de efectos en nodos),
  `export_dialog`, `audio_controls`.
- `core/commands/` — 13 comandos. Incluye las primitivas de edición
  **avanzadas**: `ripple_delete`, `roll_edit`, `slide_edit`, `slip_edit`.
- `core/engines/` — doble backend de render: `mlt_engine` (linaje MLT/Shotcut)
  y `pyav_engine` (PyAV/FFmpeg), más `frame_cache`, `spatial_compositor`.
- `core/plugins/` — sistema de descubrimiento y carga de plugins.
- `core/utils/` — interpolación de keyframes, utilidades de tiempo y math.
- Config por defecto: 30 fps, 1920x1080 (`config/settings.json`).
- Sin `requirements.txt` ni tests.

### `qwen_video_editor/` — NLE en Flet, paradigm source/program monitor

El borrador más desarrollado. Built on [Flet](https://flet.dev).

- `app/ui/monitors/` — paradigma de doble monitor: `source_monitor`,
  `program_monitor`, `video_surface`.
- `app/ui/timeline/` — timeline rica: `timeline_view`, `track_view`, `clip_view`,
  `ruler`, `playhead`, `snap_engine`.
- `app/ui/panels/` — `media_browser`, `properties_panel`, `effects_panel`,
  `keyframe_editor`, `export_dialog`.
- `app/state/app_state.py` — store de estado reactivo central.
- `core/commands/` — 12 comandos con `base_command`, `compound_command` y un
  conjunto de edición más simple (sin ripple/roll/slide/slip).
- `core/time/` — paquete dedicado: `timecode` (NTSC drop-frame),
  `fps_converter`, `time_utils`.
- `core/engines/` — `base_engine`, `mlt_engine`, `pyav_engine`, `compositor`.
- `tests/` — 9 módulos de test (vacíos).
- Config por defecto: 24 fps, 1920x1080, proxies libx264, frame cache de 512 MB,
  autosave cada 120 s, límite de undo de 100 pasos.
- `project_workspace/` se genera en runtime (medios del usuario, `Exportaciones/`,
  `AutoSave/`, cachés) y no se versiona.

> El nombre `qwen` es una etiqueta de procedencia/branding. No hay código de
> modelo, inferencia ni red en este repositorio.

## Requisitos

Python 3.13. Declarados en `qwen_video_editor/requirements.txt`:

```
flet>=0.25.0
av>=12.0.0
numpy>=1.26.0
opencv-python-headless>=4.9.0
pydantic>=2.5.0
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r qwen_video_editor/requirements.txt
```

`deep_video_editor` no declara dependencias todavía.

## Estado

Sin tests, sin CI, sin licencia. Todo el código está pendiente de escribir.
