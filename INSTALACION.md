# INSTALACION.md — Poner en marcha el editor en Linux

Guía paso a paso para instalar y ejecutar el editor desde cero en Linux
(Debian / Ubuntu y derivadas como referencia) y desde PyCharm. Las decisiones
de fondo están en [PROJECT.md](PROJECT.md), sección 15.4.

---

## 1. Requisitos

| Qué | Versión | Comprobar |
|---|---|---|
| Linux de escritorio (X11 o Wayland) | Ubuntu 22.04+, Debian 12+ o equivalente | `cat /etc/os-release` |
| Python | **3.13 recomendado**, mínimo 3.12 | `python3 --version` |
| Espacio en disco | Brutos + Piezas horneadas + caché (cuente varias veces el tamaño del material) | `df -h` |
| GPU (opcional) | NVIDIA con NVENC para codificar por hardware | `nvidia-smi` |

### Python 3.13 si la distribución trae uno más viejo

Ubuntu 22.04 / 24.04:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev
```

Otras distribuciones: `pyenv install 3.13` o el paquete oficial de la distribución.

---

## 2. Dependencias del sistema

```bash
sudo apt update
sudo apt install \
    libmpv2 \
    libgtk-3-0 libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 \
    zenity \
    fonts-dejavu \
    xdg-utils
```

| Paquete | Para qué | Si falta |
|---|---|---|
| `libmpv2` (en distribuciones viejas `libmpv1`) | Reproducción fluida (nivel 3: el pre-render del minuto) | La app sigue reproduciendo "en vivo" (nivel 2) y avisa en la barra inferior |
| `libgtk-3-0`, `libgstreamer…` | Ventana de escritorio de Flet | La ventana no abre |
| `zenity` | Selector de archivos y carpetas (importar, abrir, nuevo proyecto) | Los botones de importar/abrir no muestran el diálogo |
| `fonts-dejavu` | Fuente de la interfaz y de los textos del video por defecto | Algunos símbolos se ven como cuadros |
| `xdg-utils` | "Abrir la carpeta" de los renders | El botón no hace nada |

En Fedora: `sudo dnf install mpv-libs gtk3 gstreamer1 zenity dejavu-sans-fonts xdg-utils`.
En Arch: `sudo pacman -S mpv gtk3 gstreamer zenity ttf-dejavu xdg-utils`.

> **libmpv con otro nombre**: si la ventana avisa que no encuentra `libmpv.so.1`
> y la distribución solo trae `libmpv.so.2`, cree el enlace:
> `sudo ln -s /usr/lib/x86_64-linux-gnu/libmpv.so.2 /usr/lib/x86_64-linux-gnu/libmpv.so.1`

---

## 3. Entorno virtual y dependencias de Python

Desde la raíz del repositorio:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` fija las versiones probadas:

```
flet[desktop]==1.0.2    flet-video==1.0.2    flet-audio==1.0.2
av==18.1.0              numpy==2.5.3
opencv-python-headless==5.0.0.93             Pillow==12.3.0
```

`flet`, `flet-desktop`, `flet-video` y `flet-audio` se actualizan **juntos**:
cada uno exige la misma versión exacta de `flet`.

### Comprobar la instalación

```bash
python -c "import flet, flet_video, flet_audio, av, cv2, numpy, PIL; print('dependencias OK · av', av.__version__)"
pip show flet | grep Version                     # debe decir 1.0.2
python -c "import av; print([c for c in ('libx264','h264_nvenc','prores_ks','aac') if c in av.codecs_available])"
python main.py --help
```

La primera vez que se abre la interfaz, Flet descarga su cliente de escritorio
(unos 100 MB) en `~/.flet/`; hace falta conexión a internet solo esa vez.

---

## 4. PyCharm

1. **Abrir** la carpeta del repositorio.
2. *Settings → Project → Python Interpreter → Add Interpreter → Existing* →
   `.venv/bin/python` (o crear el entorno aquí mismo y luego instalar
   `requirements.txt` desde la terminal de PyCharm).
3. *Run → Edit Configurations → + → Python*:
   - **Script**: `main.py`
   - **Working directory**: la raíz del repositorio
   - **Parameters** (opcional): la ruta de un proyecto, por ejemplo `~/Videos/mi-serie`
4. Ejecutar. Sin parámetros abre el último proyecto usado o la pantalla de inicio.

Configuraciones útiles adicionales (mismo script, otros parámetros):

| Nombre | Parameters |
|---|---|
| Nuevo proyecto | `--nuevo ~/Videos/mi-serie` |
| Revisar disco | `--escanear ~/Videos/mi-serie` |
| Render capítulo 1 | `--render ~/Videos/mi-serie --capitulo 1` |
| Render minutos 0–5 por idioma | `--render ~/Videos/mi-serie --capitulo 1 --minutos 00-05 --por-idioma` |
| Registro detallado | agregar `--nivel-registro DEBUG` a cualquiera |

---

## 5. Primer uso

```bash
source .venv/bin/activate
python main.py --nuevo ~/Videos/mi-serie      # crea cap0001 con min00…min23 y lo abre
```

1. **Importar** (icono ⬆ del navegador): los archivos se **copian** a `brutos/`.
   Si el fps declarado no coincide con el medido, el Bruto aparece con aviso.
2. Espacio **Taller**: elegir el Bruto, marcar entrada (I) y salida (O) en
   fotogramas nativos, el fps interpretado y el método → **Crear Pieza** →
   **Hornear** (barra inferior con el progreso).
3. **Colocar en el cabezal** (capa destino de la barra de la timeline; con
   **Global** marcado va a la pista Global del capítulo).
4. Espacio **Minuto**: editar en la timeline, el monitor (asas) y el inspector.
5. **Ctrl+S** guarda (renombra archivos, gemelos y guiones).
6. Espacio **Render**: minuto actual, rango I–O o capítulo completo.

Gestos y atajos: [PROJECT.md, sección 16.6](PROJECT.md#166-gestos-y-atajos-revisión-8).

---

## 6. Dónde guarda cosas

| Ruta | Contenido | ¿Se puede borrar? |
|---|---|---|
| `PROYECTO/` | Todo el proyecto (ver PROJECT.md, sección 9) | No |
| `PROYECTO/.cache/` | Banco de vista previa, miniaturas, pre-renders, audio | Sí (se regenera) |
| `PROYECTO/.autosave/` | Instantánea de recuperación | Sí, si guardó |
| `PROYECTO/.papelera/` | Archivos reemplazados al guardar (permite deshacer tras guardar) | Sí, con la app cerrada |
| `PROYECTO/.bloqueo` | Marca de proyecto abierto | Solo si la app está cerrada y quedó por un cierre forzado (la app lo detecta sola si el proceso ya no existe) |
| `~/.config/editor/ajustes.json` | Proyectos recientes y ajustes del usuario | Sí |
| `~/.config/editor/distribucion.json` | Tamaños de paneles y espacio activo | Sí (vuelve al de fábrica) |
| `~/.config/editor/atajos.json` | Atajos propios (solo las claves que cambie) | Sí |
| `~/.flet/` | Cliente de escritorio de Flet | Sí (se descarga de nuevo) |

---

## 7. Opcional: codificación por hardware

- **NVIDIA (NVENC)**: basta el controlador propietario; el PyAV de `pip` ya trae
  `h264_nvenc` / `hevc_nvenc`. Compruebe con `nvidia-smi`.
- **Intel / AMD (VAAPI)**: el PyAV de `pip` **no** trae VAAPI. Hay que compilarlo
  contra el FFmpeg del sistema:

  ```bash
  sudo apt install vainfo libva-dev ffmpeg \
      libavcodec-dev libavformat-dev libavdevice-dev libavfilter-dev \
      libswscale-dev libswresample-dev pkg-config
  vainfo                                  # debe listar perfiles H.264
  pip install av==18.1.0 --no-binary av   # dentro del .venv
  ```

---

## 8. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError: flet` al ejecutar | PyCharm usa otro intérprete | Elegir `.venv/bin/python` (paso 4.2) |
| La ventana no abre, error de GTK | Faltan librerías de escritorio | Paso 2 |
| "La reproducción fluida no está disponible (¿falta libmpv?)" | Falta `libmpv` | `sudo apt install libmpv2` (o el enlace del paso 2) |
| Importar / Abrir no muestran diálogo | Falta `zenity` | `sudo apt install zenity` |
| "Proyecto en uso" al abrir | Otra ventana lo tiene abierto, o quedó `.bloqueo` de un cierre forzado en otro equipo | Cerrar la otra instancia; abrir en solo lectura; si está seguro, borrar `PROYECTO/.bloqueo` |
| Al abrir pregunta "Recuperar trabajo" | La app se cerró sin guardar | **Restaurar** y luego Ctrl+S; **Descartar** borra la instantánea |
| Los símbolos se ven como cuadros | Faltan fuentes | `sudo apt install fonts-dejavu` |
| Sin sonido al reproducir | Salida de audio del sistema | La imagen sigue a tiempo real; revise el mezclador del sistema |
| Render lento | Codificación por software | NVENC o VAAPI (sección 7) |
