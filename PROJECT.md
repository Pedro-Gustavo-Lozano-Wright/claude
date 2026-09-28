# Editor de video por capítulos y minutos

Documentación central del proyecto: qué es, cómo se organiza, cómo se usa cada
parte de la interfaz, cómo guarda en disco y cómo está construido el código.
La instalación y los problemas frecuentes están en el [README](README.md).

## Índice

1. [Qué es](#1-qué-es)
2. [Conceptos](#2-conceptos)
3. [Estándar HD720-24](#3-estándar-hd720-24)
4. [Tiempo](#4-tiempo)
5. [Espacio](#5-espacio)
6. [El proyecto en disco](#6-el-proyecto-en-disco)
7. [Guardar y sincronizar con el disco](#7-guardar-y-sincronizar-con-el-disco)
8. [La ventana](#8-la-ventana)
9. [Taller](#9-taller)
10. [Timeline y edición](#10-timeline-y-edición)
11. [Monitor y vista previa](#11-monitor-y-vista-previa)
12. [Inspector: propiedades, animación y efectos](#12-inspector-propiedades-animación-y-efectos)
13. [Texto y subtítulos](#13-texto-y-subtítulos)
14. [Audio](#14-audio)
15. [Idiomas](#15-idiomas)
16. [Render y entregables](#16-render-y-entregables)
17. [Shorts verticales 9:16](#17-shorts-verticales-916)
18. [Proyecto, capítulos y mantenimiento](#18-proyecto-capítulos-y-mantenimiento)
19. [Atajos y gestos](#19-atajos-y-gestos)
20. [Modos sin interfaz](#20-modos-sin-interfaz)
21. [Arquitectura del código](#21-arquitectura-del-código)
22. [Reglas de integración](#22-reglas-de-integración)
23. [Límites conocidos](#23-límites-conocidos)

---

## 1. Qué es

Un editor de video de escritorio para **Linux**, escrito en **Python** con la
interfaz en **Flet**, que organiza todo **por tiempo**:

- Un **proyecto** contiene hasta **1000 capítulos**. Cada capítulo mide
  **exactamente 24 minutos** y tiene **una carpeta por minuto** (`min00`–`min23`).
- Cada archivo vive en la carpeta del minuto donde empieza y **su nombre dice el
  instante exacto en que aparece**. Con el programa cerrado, las carpetas ya
  cuentan la historia.
- Se edita **un minuto a la vez** para el trabajo fino, o el capítulo completo
  para el ritmo general. Solo hay **un capítulo abierto en memoria**.
- El material se prepara en un **Taller** (recortar, convertir a 24 fps,
  hornear) antes de llegar a la timeline.
- La composición es en **píxeles sobre un lienzo 1280×720 (16:9)**, con capas
  apiladas, transparencias, keyframes, efectos y transiciones.
- El render puede ser **de un minuto, de un rango o del capítulo completo**, y
  **solo se vuelven a renderizar los minutos que cambiaron**.
- Se entregan videos para YouTube (720p, −14 LUFS, subtítulos `.srt` y
  capítulos) y **Shorts verticales 9:16** recortados del capítulo.

Principios:

| Principio | Qué significa |
|---|---|
| Nombre = historia, gemelo = puesta en escena | El nombre del archivo guarda el tiempo; un `.json` gemelo guarda el espacio, los keyframes y los efectos |
| Todo cambio es un comando | Cada edición se puede deshacer y rehacer |
| El disco se reconcilia al guardar | Arrastrar no renombra archivos; guardar sí, de forma atómica |
| Carpetas autosuficientes | Cada minuto contiene copias reales de sus medios |
| Núcleo sin interfaz | `editor/core` no depende de Flet: el render y otros modos funcionan sin ventana |
| Español en todo el dominio | Un concepto, un nombre, en código, archivos y pantalla |

---

## 2. Conceptos

| Concepto | Qué es | En disco |
|---|---|---|
| **Proyecto** | La serie completa | `MiSerie/` con `_proyecto.json` |
| **Capítulo** | 24 minutos exactos | `cap0001/` … `cap1000/` con `_capitulo.json` |
| **Minuto** | Ventana de 60 s del capítulo | `cap0001/min00/` … `min23/` con `_minuto.json` y `_guion.txt` |
| **Global** | Pistas del capítulo que abarcan varios minutos (música, logo fijo) | `cap0001/global/` |
| **Bruto** | Archivo original importado; nunca se modifica | `brutos/video\|audio\|imagen/bru0001_nombre__id.ext` |
| **Taller** | Espacio para preparar material | `taller/` |
| **Pieza** | Tramos de un Bruto convertidos a 24 fps y horneados | `taller/pie0001_nombre__id/` |
| **Elemento** | Una ventana de tiempo sobre un medio, colocada en una capa del lienzo y la timeline | Archivo de medio + gemelo `.json` en el minuto o en `global/` |
| **Capa** | `V1`–`V9` (video e imagen), `A1`–`A9` (audio), `T1`–`T9` (texto) | Parte del nombre del Elemento |
| **Keyframe** | Valor de una propiedad en un fotograma, con su curva | Dentro del gemelo |
| **Efecto** | Proceso de imagen con parámetros animables | Dentro del gemelo |
| **Transición** | Entrada de un Elemento sobre el anterior de su capa | Dentro del gemelo del entrante |
| **Marcador** | Punto con nombre y color en el capítulo | `_capitulo.json` |
| **Short** | Recorte vertical 9:16 de un rango del capítulo | `cap0001/shorts/` |
| **Render** | Entregable de un minuto, rango o capítulo | `cap0001/render/` |
| **Recursos** | Fuentes tipográficas y LUT | `recursos/fuentes/`, `recursos/luts/` |

Reglas de nombres:

1. Los archivos de **control** empiezan con `_` y quedan primeros al ordenar.
2. **Ceros a la izquierda en todo**: el orden alfabético es el cronológico.
3. Minutos del **00 al 23**, como un reloj: `min02_seg12` es `02:12`.
4. **IDs** de 6 hexadecimales, únicos en todo el proyecto y permanentes
   (Brutos, Piezas, Elementos y Shorts comparten el mismo espacio de IDs).
5. **Nombre descriptivo**: minúsculas, números y guiones, hasta 32 caracteres
   (lo que se escribe se normaliza solo: "Mi Toma" → `mi-toma`).
6. Capítulos `cap0001` a `cap1000`; en pantalla, "Capítulo 1" más su título.

---

## 3. Estándar HD720-24

| Parámetro | Valor |
|---|---|
| Lienzo | **1280 × 720 px, 16:9**, único formato de edición |
| Origen | (0, 0) arriba a la izquierda; X a la derecha, Y hacia abajo |
| Fotogramas por segundo | **24 constantes** |
| Capítulo | 24 minutos = **34 560 fotogramas** |
| Minuto | **1440 fotogramas** |
| Composición interna | RGBA con alfa premultiplicado, sRGB / BT.709 8 bits |
| Audio | 48 kHz estéreo |
| Render | H.264 CRF 18 `medium`, yuv420p, AAC 192 kbps, `.mp4` |
| Short | 720 × 1280 px, 9:16, 24 fps |
| Pieza horneada | Resolución original hasta 2560 × 1440; H.264 CRF 14 (`.mp4`) o ProRes 4444 con alfa (`.mov`) |
| Banco de vista previa | 256 × 144 px, 10 fps; JPEG (opaco) o WebP (con alfa) |
| Pre-render de reproducción | 960 × 540, 24 fps, H.264 `ultrafast` |

**Regla del marco espacial**: lo que está dentro del lienzo se ve; lo que está
fuera existe, se guarda y se anima, pero no se muestra ni se renderiza.

**Regla del marco temporal**: el capítulo mide siempre 24:00. Lo que un Elemento
de `min23` desborde más allá de 24:00 se guarda pero no se reproduce ni se
renderiza (la timeline lo muestra rayado). El tiempo vacío se renderiza en
negro y silencio, así cada minuto dura siempre 1440 fotogramas.

Dónde vive el estándar:

- `config/estandar.json`: valores para **proyectos nuevos**.
- `_proyecto.json`: **copia propia de cada proyecto**; es la que manda al editar
  y renderizar ese proyecto. Ahí se activa la codificación por hardware NVIDIA
  (`"render": {"aceleracion": "nvenc"}`).

---

## 4. Tiempo

### 4.1 Unidades

```
Proyecto → Capítulo (24 min) → Minuto (60 s) → Segundo (24 f) → Fotograma
  ≤ 1000      34 560 f           1440 f
```

- Internamente todo es un **número entero de fotogramas del capítulo**.
- Minuto, segundo, fotograma y nombre son vistas calculadas:
  `3176 = minuto 02, segundo 12, fotograma 08 = "min02_seg12f08"` (en pantalla,
  `02:12.08`).
- Los **keyframes** se guardan **relativos al inicio del Elemento**: mover el
  Elemento no obliga a reescribirlos.

### 4.2 Tiempo de un Elemento

| Propiedad | Unidad | Significado |
|---|---|---|
| `inicio` | fotograma del capítulo | Sale del nombre del archivo |
| `duracion` | fotogramas | Sale del nombre del archivo |
| `fuente_entrada` | fotograma de la Pieza | Desde dónde se usa la Pieza (incluye el segundo de asa) |
| `velocidad` | factor | 1 normal; negativa = reversa; 0,05–8 |
| `congelado` | — | Muestra siempre el mismo fotograma de la fuente |

**Rampas de velocidad**: la velocidad también se anima con keyframes (no en
reversa ni en congelado). La fuente que avanza es la integral de la velocidad,
así que recortes, ripple y el aviso de "fuente insuficiente" cuentan lo que la
rampa consume de verdad.

### 4.3 Minutos como ventanas

- El capítulo es la línea de tiempo real y continua; cada minuto es una
  ventana de 60 s con su carpeta.
- Un Elemento vive en la carpeta del minuto donde **empieza** y puede
  **desbordarse** al siguiente, que lo muestra como fantasma ("entra desde
  min02").
- **Global** guarda lo que abarca varios minutos; sus pistas se ven bajo las de
  los minutos (`GV1`, `GA1`, `GT1`…).

### 4.4 Capas

- Dos Elementos **no se solapan en la misma capa**, salvo durante la
  transición de entrada del segundo.
- Orden de apilado: V1 (fondo) … V9, después T1 … T9 (textos siempre encima),
  primero lo de los minutos y luego lo de Global en el mismo orden.
- Las capas A no tienen orden visual: se mezclan todas.
- Cada capa del capítulo tiene estado: **visible**, **silenciada**, **solo**,
  **bloqueada** e **idioma** (sección 15).

---

## 5. Espacio

```
(0,0) ───────────────────── X → ─────────── (1280,0)
  │  ┌─────────────────────────────────────┐
  Y  │          LIENZO 1280 × 720          │
  ↓  │    (200,150)┌──────────┐            │
  │  │             │ Elemento │            │
  │  │             └──────────┘            │
  │  └─────────────────────────────────────┘ ┌────┐
(0,720)                             (1280,720)│fuera: existe, no se ve
```

| Propiedad | Unidad | Por defecto | Significado |
|---|---|---|---|
| `x`, `y` | px del lienzo | 0, 0 | Dónde cae el ancla |
| `ancla_x`, `ancla_y` | px del Elemento | 0, 0 | Punto de colocación, giro y escala |
| `escala_x`, `escala_y` | factor | 1 | Negativa = espejo |
| `rotacion` | grados | 0 | Sentido horario |
| `recorte` | px (izq, arr, der, abj) | 0 | Se recorta antes de colocar |
| `opacidad` | 0–1 | 1 | |
| `mezcla` | modo | normal | normal, multiplicar, pantalla, superponer, sumar |

- Todas las propiedades numéricas son **animables**.
- Al mover el ancla, el editor compensa `x, y` para que el Elemento no salte.
- Al **colocar**, el Elemento se **encaja** en el lienzo conservando su
  proporción (un video 1080p entra a escala 0,667, centrado).
- Cálculo: `M = Trasladar(x, y) · Rotar · Escalar · Trasladar(−ancla)`. Lo que
  no toca el lienzo ni se decodifica; lo que sí, se transforma solo en su
  región visible. Lo que se ve es lo que se exporta.

---

## 6. El proyecto en disco

### 6.1 Árbol

```
MiSerie/
├── _proyecto.json                estándar propio, idiomas, índice de capítulos, contador de IDs
├── brutos/                       originales copiados al importar; nunca se modifican
│   ├── video/   bru0001_toma-calle__7c2185.mp4
│   ├── audio/   bru0002_entrevista__91be07.wav
│   └── imagen/  bru0003_logo__0f3a6b.png
├── taller/
│   └── pie0001_puerta-abre__5e1c3a/
│       ├── _pieza.json           receta: tramos, fps, método, copias en capítulos
│       ├── _horneado.json        resultado del último horneado (automático)
│       └── pie0001_puerta-abre__5e1c3a.mp4   horneado (.mov si tiene alfa)
├── recursos/
│   ├── fuentes/                  .ttf / .otf de los textos
│   └── luts/                     .cube
├── cap0001/
│   ├── _capitulo.json            título, estado de capas, marcadores, estado de minutos
│   ├── global/                   Elementos que abarcan varios minutos
│   ├── min00/ … min23/
│   │   ├── _minuto.json          estado de trabajo y notas
│   │   ├── _guion.txt            resumen legible, se regenera al guardar
│   │   ├── min00_seg00f00_dur12s08_V1_ciudad-amanece__4b7e19.mp4
│   │   ├── min00_seg00f00_dur12s08_V1_ciudad-amanece__4b7e19.json
│   │   └── min00_seg14f00_dur03s00_T1_titulo-capitulo__d4e25c.json
│   ├── render/
│   │   ├── _renders.json         entregables y último render de cada minuto y Short (automático)
│   │   ├── cap0001_completo_v002.mp4
│   │   ├── cap0001_completo_v002_es.srt
│   │   └── cap0001_completo_v002.txt
│   └── shorts/
│       ├── min02_seg10f00_dur45s00_momento-clave__b71c4d.json       receta
│       └── min02_seg10f00_dur45s00_momento-clave__b71c4d_v001.mp4   720×1280
├── .bloqueo                      instancia que tiene el proyecto abierto
├── .diario/                      operaciones de disco en curso
├── .papelera/                    lo reemplazado al guardar, con su ruta original
├── .autosave/                    instantánea de recuperación
└── .cache/                       se puede borrar: banco, miniaturas, ondas, pre-renders, audio, minutos renderizados
```

### 6.2 Nombre de un Elemento

```
min02_seg12f08_dur05s00_V2_puerta-abre__a3f90e.mov
 │     │    │    │        │   │            │
 │     │    │    │        │   │            └ ID
 │     │    │    │        │   └ nombre descriptivo
 │     │    │    │        └ capa
 │     │    │    └ duración (dur01m05s00 si ≥ 1 min)
 │     │    └ fotograma de inicio (f00–f23)
 │     └ segundo de inicio
 └ minuto de inicio (en global/, el minuto del capítulo)
```

| Objeto | Formato | Ejemplo |
|---|---|---|
| Bruto | `bruNNNN_nombre__id.ext` | `bru0001_toma-calle__7c2185.mp4` |
| Pieza | `pieNNNN_nombre__id` (carpeta y archivo) | `pie0001_puerta-abre__5e1c3a.mov` |
| Render | `capCCCC_{minMM \| minMM-MM \| completo}_vNNN[_idioma].ext` | `cap0001_min05-08_v001.mp4` |
| Short | igual que un Elemento sin capa; `_vNNN.mp4` para el render | `min02_seg10f00_dur45s00_momento-clave__b71c4d_v001.mp4` |

### 6.3 Gemelo de un Elemento

```json
{
  "id": "a3f90e",
  "fuente": { "tipo": "pieza", "ref": "5e1c3a", "version": 3 },
  "tiempo": { "inicio": "min02_seg12f08", "duracion": "dur05s00",
              "fuente_entrada": 24, "velocidad": 1.0 },
  "espacio": { "x": 200, "y": 150, "ancla_x": 0, "ancla_y": 0,
               "escala_x": 1.0, "escala_y": 1.0, "rotacion": 0,
               "recorte": [0, 0, 0, 0], "opacidad": 1.0, "mezcla": "normal" },
  "keyframes": { "x": [ { "f": 0, "valor": -400, "curva": "ease-out" },
                        { "f": 24, "valor": 200 } ] },
  "efectos": [],
  "transicion_entrada": { "tipo": "fundido", "duracion": 12 },
  "audio": { "volumen": 1.0, "paneo": 0.0, "silenciado": false },
  "estado": { "activo": true, "bloqueado": false }
}
```

- `fuente.version` detecta copias de una Pieza que se volvió a hornear.
- Un Elemento de **texto** no tiene archivo de medio: su `.json` es a la vez
  contenido y gemelo, con una sección `texto` (sección 13).
- Si falta un gemelo, el escáner recupera tiempo y capa del nombre y usa
  valores por defecto para el resto.

### 6.4 Qué se guarda dónde

| Dónde | Qué |
|---|---|
| Carpeta | Capítulo y minuto |
| Nombre del archivo | Inicio, duración, capa, nombre e ID |
| Gemelo `.json` | Espacio, keyframes, efectos, transición, audio, estado |
| `_minuto.json` | Estado de trabajo (listo) y notas |
| `_capitulo.json` | Título, estado de capas (con idioma), marcadores |
| `_proyecto.json` | Estándar, idiomas, índice de capítulos |
| `_guion.txt` | Reflejo legible del minuto; nunca se lee |
| `_renders.json`, `_horneado.json` | Estado **automático**: lo escriben los servicios en el momento |

**Estado del usuario y estado automático**: lo que el usuario edita (Elementos,
capas, marcadores, Shorts, recetas, títulos, idiomas) cambia solo con comandos
y se escribe al **guardar**. Lo que producen los servicios (horneados, renders,
análisis) se escribe **en el momento** y no se deshace. Deshacer nunca revierte
estado automático y los servicios nunca escriben archivos del usuario.

Ejemplo de `_guion.txt`:

```
MINUTO 02 · cap0001 · lienzo 1280×720 · 24 fps
02:00.00  V1  ciudad-amanece   12s08  pos (0,0)       esc 1.00
02:12.08  V2  puerta-abre       5s00  pos (-400,150)→(200,150)
02:14.00  T1  titulo-capitulo   3s00  pos (440,600)   texto
02:17.08  A1  dialogo-juan     40s00  —               vol 100 %
```

---

## 7. Guardar y sincronizar con el disco

El modelo en memoria es la verdad mientras se edita; al guardar, el disco pasa
a ser su reflejo legible.

| Situación | Cómo se resuelve |
|---|---|
| Arrastrar y editar | No toca el disco; se reconcilia al **guardar** (Ctrl+S) |
| Elemento que cambia de minuto o de nombre | El guardado mueve y renombra contenido y gemelo juntos, en dos fases con nombres temporales (intercambios A↔B incluidos) |
| Corte de luz a mitad de un guardado | El **diario** (`.diario/`) escribe el plan antes de ejecutarlo; al abrir se completa |
| Deshacer después de guardar | Lo reemplazado va a `.papelera/`; el siguiente guardado lo recupera |
| Cambios hechos fuera del programa | Cada archivo tiene su firma conocida: si cambió, **no se sobrescribe**. Un diálogo lista los conflictos: recargar desde el disco o conservar la versión del programa |
| Dos instancias sobre el mismo proyecto | `.bloqueo`: la segunda solo puede abrir en **solo lectura** (ni edita, ni guarda, ni renderiza) |
| Cierre inesperado | **Autosave** cada 120 s en `.autosave/` (sin renombrar nada). Al abrir, si la instantánea es más reciente, se ofrece **restaurar** o **descartar** |
| Trabajos interrumpidos | Al abrir se borran los temporales de renders, Shorts, horneados, caché e importaciones que quedaron a medias |
| Medio que falta | En la imagen aparece un **marco rojo** con su nombre; el informe al abrir lista los medios fuera de línea |

**Materialización**: colocar una Pieza en un minuto **copia** su horneado a la
carpeta del minuto con el nombre del Elemento. La misma Pieza en tres minutos
son tres copias. Mientras no se guarda, la vista previa lee el horneado del
Taller. Al volver a hornear una Pieza, el **índice de referencias**
(Bruto → Piezas → Elementos → minuto) actualiza todas sus copias.

**Un capítulo en memoria**: cambiar o crear un capítulo pide guardar antes;
el anterior se descarga y el historial empieza vacío. Las consultas sobre
capítulos no cargados ("¿qué usa este Bruto?", "¿qué idiomas usa?") se
responden leyendo el disco. Si una tarea de fondo termina después de cambiar de
capítulo, su resultado no se aplica al capítulo nuevo (se avisa), y un render
de otro capítulo se anota directamente en su `_renders.json`.

---

## 8. La ventana

### 8.1 Pantalla de inicio

Sin proyecto abierto: **Nuevo proyecto** (elige carpeta y nombre; crea
`cap0001` con sus 24 minutos), **Abrir proyecto** y la lista de **recientes**.
`python main.py` abre directamente el último proyecto usado.

### 8.2 Secciones

```
┌──────────────┬──────────────────────────────────┬──────────────┐
│ NAVEGADOR    │  MONITOR / LIENZO                │ INSPECTOR    │
│ capítulos    │                                  │ propiedades  │
│ minutos      │                                  │ keyframes    │
│ Brutos       │                                  │ curvas       │
│ Taller       │                                  │ historial    │
├──────────────┴──────────────────────────────────┴──────────────┤
│ MAPA DEL CAPÍTULO  [00●][01◐][02○] … [23○]                     │
├────────────────────────────────────────────────────────────────┤
│ TIMELINE                                                       │
├────────────────────────────────────────────────────────────────┤
│ barra de tareas: progreso, cancelar, avisos                    │
└────────────────────────────────────────────────────────────────┘
```

- Barra superior: nombre del proyecto (• si hay cambios sin guardar; "solo
  lectura" si corresponde), **espacios de trabajo**, deshacer, rehacer,
  guardar, menú **☰ Proyecto**, restablecer distribución y cerrar proyecto.
- Cada sección cambia de tamaño arrastrando su divisor y se pliega con doble
  clic. La distribución se recuerda por espacio de trabajo.
- La **barra de tareas** muestra la tarea de fondo en curso, su progreso,
  cuántas esperan y un botón para cancelarla. Los renders pedidos seguidos
  esperan su turno ahí.

### 8.3 Espacios de trabajo

| Espacio | Para qué | Muestra |
|---|---|---|
| **Taller** | Preparar Piezas | Taller y monitor lado a lado, navegador, timeline |
| **Minuto** | Edición fina | Navegador, monitor, inspector, mapa, timeline por minuto |
| **Capítulo** | Ritmo general | Timeline con los 24 minutos |
| **Shorts** | Recortes 9:16 | Panel de Shorts, monitor con la ventana vertical, timeline |
| **Render** | Entregables | Panel de render, mapa |

### 8.4 Navegador

- **Capítulos**: elegir capítulo (pide guardar si hay cambios), **nuevo
  capítulo** y **título** del capítulo.
- **Minutos** con sus dos estados (trabajo y render, igual que el mapa); clic
  para ir.
- **Brutos**: importar (⬆), con icono por tipo y aviso si el fps necesita
  revisión; clic para abrirlo en el Taller; **colocar en el cabezal**.
- **Piezas** del Taller: abrir y colocar.
- **Importar subtítulos `.srt`** (sección 13).

### 8.5 Mapa del capítulo

24 celdas, una por minuto:

| Qué | Cómo se ve | Valores |
|---|---|---|
| Trabajo | Relleno | vacío (gris) · en progreso (ámbar) · listo (azul) |
| Render | Punto en la esquina | sin render · desactualizado (rojo) · al día (verde) |
| Reproducción | Barra inferior | pre-render listo (verde) o no |

**Clic**: ir al minuto. **Doble clic**: marcar o desmarcar "listo". **Clic
derecho en dos celdas**: intercambiar esos dos minutos completos.

---

## 9. Taller

Del **Bruto** a la **Pieza** en 24 fps:

```
BRUTO (fps nativo) → TALLER (recorte en fotogramas nativos) → HORNEADO → PIEZA (24 fps + asas)
```

### 9.1 Importar

Importar **copia** el archivo a `brutos/` (el proyecto es autosuficiente) y lo
analiza: `fps_detectado` (metadatos), `fps_medido` (marcas de tiempo reales) y
si el fps es **variable** (típico de celulares). Si no coinciden, el Bruto
aparece con aviso. Antes de copiar se comprueba el espacio en disco.

### 9.2 Recortar y crear Piezas

- El visor del Taller muestra el Bruto en **fotogramas nativos**; ← → avanzan
  un fotograma nativo.
- **I / O** marcan entrada y salida (con el foco en el Taller).
- **fps interpretado**: el usuario puede corregirlo (un archivo que dice 30 y es
  29,97).
- **Crear Pieza** con el tramo marcado, o **Añadir tramo** a una Pieza
  existente (una Pieza puede tener varios tramos seguidos).
- Imágenes y audio se pueden **colocar directo** sin crear Pieza.

### 9.3 Conversión a 24 fps

| Método | Qué hace | Duración | Uso típico |
|---|---|---|---|
| **Tiempo real** (por defecto) | Descarta o duplica fotogramas según su marca de tiempo | Igual | General, fps variable |
| **Conformar** | Cada fotograma de la fuente pasa a ser uno de 24 fps | Cambia | 23,976 → 24, 25 → 24 |
| **Cámara lenta** | Conformar aplicado a fuentes rápidas | Más larga | 60 → 24 = 2,5× más lento |
| **Mezcla de fotogramas** | Fusiona fotogramas vecinos | Igual | 30 → 24 sin saltos |
| **Interpolación** | Genera intermedios por flujo óptico | Igual | Tomas difíciles (más lento) |

Cuando el método cambia la duración, el **audio** se trata según la Pieza:
**estirar conservando el tono** (por defecto), estirar cambiando el tono o
silenciar.

### 9.4 Hornear

**Hornear** produce el archivo normalizado de la Pieza (24 fps, 48 kHz,
resolución original hasta 2560×1440, con alfa si la fuente lo tiene) con **un
segundo de asa** antes y después del tramo si el Bruto lo permite: margen para
recortar y hacer slip sin volver al Taller. Los tramos con otra proporción se
encajan con bandas. Al terminar se generan el banco de vista previa, las
miniaturas y la forma de onda. Si la Pieza ya estaba colocada, todas sus copias
se actualizan. Doble clic en un Elemento de la timeline abre su Pieza.

### 9.5 Análisis

| Acción | Resultado |
|---|---|
| **Buscar escenas** | Lista de cortes de plano del Bruto; clic para ir |
| **Buscar silencios** | Tramos en silencio (segundos); útil para cortar voz |
| **Sincronizar audio externo** | Con un Elemento elegido en la timeline, coloca el audio del Bruto alineado por forma de onda (con su confianza) en la capa de destino de audio |
| **Reducir ruido** | Crea un Bruto nuevo con el ruido de fondo reducido (puerta espectral); el original no cambia |

---

## 10. Timeline y edición

### 10.1 La timeline

- **Zoom**: capítulo (24 minutos), minuto (60 s), segundos (~10 s), fotograma
  (~1 s). `=` / `−` o el selector. En los dos últimos, la rueda desplaza
  (Ctrl + rueda: zoom).
- **Pistas**: las de los minutos y debajo las de Global. Altura ajustable.
  Cabecera de cada capa: **ver**, **silenciar**, **solo**, **bloquear** y, en
  capas A y T, **idioma** (sección 15).
- Dentro de cada Elemento: **miniaturas** (video), **forma de onda** (audio),
  la **línea de volumen** y un **triángulo** donde hay transición de entrada.
- **Fantasmas** de lo que entra desbordado del minuto anterior; rayado lo que
  pasa de 24:00.
- **Regla**: clic o arrastrar mueve el cabezal (sin cambiar la selección); cerca
  de un marcador, el cabezal se pega a él.
- **Marcas I / O** (rango sombreado) y **marcadores** con nombre y color.

### 10.2 Barra de la timeline

| Control | Qué hace |
|---|---|
| Herramientas | Selección (V), cuchilla (C), ripple (B), roll (N), slip (Y), slide (U) |
| **Imán** | Pega a bordes de Elementos, cabezal, marcadores e inicio de cada minuto |
| **Marcador** | Pone un marcador en el cabezal o edita el que hay: nombre, color o quitar (M lo pone rápido) |
| **T** | Texto simple o una plantilla (título, rótulo, subtítulo, créditos) |
| **Quitar rango I–O** | Levanta lo que hay entre I y O en las capas de los minutos (con Shift: **extrae**, cerrando el hueco) |
| **Más** | Pegar insertando · pegar sobrescribiendo · separar audio · congelar fotograma · cerrar huecos del minuto |
| Destino V/T y A | Capa donde se colocan Piezas y Brutos, y la de audio |
| **Global** | Colocar en las pistas Global del capítulo |
| **Buscar** (Ctrl+F) | Busca Elementos por nombre en el capítulo; Enter pasa al siguiente |

### 10.3 Operaciones

| Operación | Cómo | Qué cambia | Qué queda fijo |
|---|---|---|---|
| **Mover** | Arrastrar el cuerpo (a otra pista del mismo tipo también) | Posición | Contenido |
| **Recortar** | Arrastrar un borde | Entrada o salida | Lo demás; queda hueco |
| **Ripple** | Herramienta ripple en un borde | Entrada o salida | Lo que sigue en el minuto se corre (todas las capas) |
| **Roll** | Herramienta roll en un corte | El corte entre dos Elementos | Duración total |
| **Slip** | Herramienta slip en el cuerpo | Qué parte de la fuente se ve | Posición |
| **Slide** | Herramienta slide en el cuerpo | Posición | Contenido; los vecinos se ajustan |
| **Cuchilla** | Clic con la cuchilla, o S en el cabezal | Divide en dos | — |
| **Selección múltiple** | Shift + clic | Mover y recortar el grupo a la vez, un solo paso de deshacer | — |
| **Quitar** / **Quitar con ripple** | Supr / Shift+Supr | Borra (y cierra el hueco en la misma capa) | — |
| **Copiar, pegar, duplicar** | Ctrl+C, Ctrl+V (en el cabezal), Ctrl+D (justo después) | — | — |
| **Pegar insertando** | Menú Más | Divide lo que cruza el cabezal y corre lo posterior | — |
| **Pegar sobrescribiendo** | Menú Más | Recorta lo que tapa | — |
| **Separar audio** | Menú Más, con un video elegido | Crea un Elemento A con su sonido; el video queda mudo | — |
| **Congelar fotograma** | Menú Más, con un video bajo el cabezal | Inserta 2 s de imagen fija y corre lo que sigue | — |
| **Cerrar huecos** | Menú Más | En cada capa del minuto, cada Elemento empieza donde termina el anterior | — |
| **Intercambiar minutos** | Clic derecho en dos celdas del mapa | Todo el contenido de ambos | — |
| **Pasar a Global / a los minutos** | Inspector | Dónde vive el Elemento | Instante y capa |
| **Volumen** | Alt + arrastrar en un audio | La línea de volumen sigue al puntero | — |
| **Transición** | Inspector, sección Transición | Tipo, duración, dirección | — |

Si una edición viola una regla (solapamiento, capa bloqueada, fuente
insuficiente), aparece un aviso y **no cambia nada**. Los arrastres se fusionan:
al soltar queda **un solo paso** de deshacer. El historial guarda 100 pasos.

---

## 11. Monitor y vista previa

### 11.1 Monitor

- **Mesa de trabajo** gris alrededor del lienzo: lo que está fuera se ve
  atenuado al editar.
- **Asas** sobre el Elemento seleccionado: mover, escalar (Shift: libre), girar
  y mover el **ancla**. Clic selecciona lo de más arriba.
- **Imán** a bordes y centro del lienzo y de otros Elementos.
- Botones: **zoom** del lienzo (encajar, 25 %, 50 %, 100 %, 200 %),
  **márgenes seguros** (acción 5 %, títulos 10 %), **guía 9:16**, **señal**
  (medidores de nivel, histograma RGB y forma de onda de luminancia) y
  **Escucha** (idioma que suena y cuyos subtítulos se ven).
- Transporte: reproducir (Espacio o L), fotograma anterior y siguiente,
  inicio de minuto, minuto siguiente y el timecode editable.
- Alt + flechas mueve 1 px; Alt + Shift + flechas, 10 px.

### 11.2 Niveles de vista previa

| Nivel | Cuándo | Qué muestra |
|---|---|---|
| 0 · Banco | Al hornear o importar | 256×144 a 10 fps, miniaturas y forma de onda en `.cache/` |
| 1 · Scrubbing | Al mover el cabezal | Composición rápida desde el banco |
| 2 · En vivo | Reproduciendo sin pre-render | Composición del banco a ~12 fps, con el **audio como reloj**: si la imagen se atrasa, salta fotogramas |
| 3 · Pre-render | Reproduciendo con el minuto listo | Video del minuto a 960×540 y 24 fps, generado en segundo plano |
| 4 · Exacto | En pausa | Fotograma a calidad final desde los archivos reales |

El pre-render de cada minuto tiene una **huella** (lo que cambia su imagen,
su audio y los subtítulos del idioma que se escucha); si la huella cambia, se
regenera solo. Sin `libmpv` o sin salida de sonido, la reproducción sigue en el
nivel 2 con reloj propio.

---

## 12. Inspector: propiedades, animación y efectos

### 12.1 Propiedades

Con un Elemento elegido (el inspector edita uno a la vez):

- **General**: nombre, activo, bloqueado, pasar a Global o a los minutos.
- **Tiempo**: velocidad (animable: rampas).
- **Espacio**: x, y, ancla, escala, rotación, opacidad (animables) y modo de
  mezcla.
- **Audio**: volumen (0–200 %) y paneo (animables), silenciado, fundidos de
  entrada y salida.
- **Texto** (en capas T): sección 13.

### 12.2 Keyframes

Cada propiedad animable muestra su valor **en el cabezal**, un rombo (◆ hay
keyframe aquí, ◇ no) y flechas para saltar al keyframe anterior o siguiente.
Si la propiedad ya tiene keyframes, cambiar el valor pone uno en el cabezal; si
no, cambia el valor base. **K** pone un keyframe de la propiedad activa.

El **editor de curvas** dibuja la propiedad activa (también parámetros de
efectos) a lo largo del Elemento: clic en un rombo lo elige, arrastrarlo en
horizontal lo mueve en el tiempo, y el selector cambia la curva del tramo que
empieza ahí: constante, lineal, ease-in, ease-out, ease-in-out o bezier (con
sus dos puntos de control).

### 12.3 Presets

| Preset | Qué hace | Para |
|---|---|---|
| **Ken Burns** | Zoom lento de 1 a 1,15 con el ancla centrada | Imágenes y video |
| **Entrada / Salida** | Fundido, deslizar o zoom al principio o al final (12 fotogramas) | Cualquier visual |
| **Estabilizar** | Mide el movimiento de cámara (flujo óptico) y lo compensa con keyframes de posición y giro, ampliando un 6 % para ocultar bordes | Video de hasta 60 s a velocidad normal (tarea de fondo) |
| **Bajar con la voz** | Keyframes de volumen que bajan la música 12 dB mientras hay voz | Audio de música (sección 14) |

Cada preset es **un paso** de deshacer y deja keyframes normales, editables
después.

### 12.4 Transiciones

La transición va en el Elemento **entrante**; su duración es el solape con el
anterior de la misma capa.

| Tipo | Dirección |
|---|---|
| Fundido | — |
| Deslizamiento | izquierda, derecha, arriba, abajo |
| Zoom | — |
| Barrido | izquierda, derecha, arriba, abajo |
| Fundido a negro | — (el saliente se oscurece y el entrante aparece desde negro) |

### 12.5 Efectos

Pila ordenada por Elemento: **agregar**, activar o desactivar, **subir** y
quitar. Los parámetros numéricos son animables.

| Efecto | Parámetros | Opciones |
|---|---|---|
| Brillo | valor −1…1 | |
| Contraste | valor −1…1 | |
| Saturación | valor −1…1 | |
| Temperatura | valor −1…1 | |
| LUT (.cube) | intensidad 0…1 | archivo de `recursos/luts/` |
| Desenfoque | radio 0…100 px | |
| Nitidez | cantidad 0…2 | |
| Croma | tolerancia, suavidad | color (por defecto verde) |
| Máscara | centro x/y, ancho, alto, suavidad, invertir | forma: elipse o rectángulo |
| Viñeta | intensidad, radio | |

La máscara, animada, sirve para seguir y ocultar algo (una cara, un logo).

---

## 13. Texto y subtítulos

### 13.1 Elementos de texto

Botón **T** de la timeline: texto simple o una **plantilla**:

| Plantilla | Estilo | Animación |
|---|---|---|
| Título centrado | 80 px, caja centrada, sombra | entra con escala, sale con fundido |
| Rótulo inferior | 40 px, alineado a la izquierda abajo | desliza hacia arriba, sale con fundido |
| Subtítulo | 40 px con contorno, centrado abajo | sin animación, 3 s |
| Créditos | 36 px, interlineado amplio | fundido, 6 s |

En el inspector: texto (varias líneas), tamaño, color, contorno, alineación
(izquierda, centro, derecha) y **animaciones de entrada y salida**: ninguna,
fundido, deslizar hacia arriba o abajo, máquina de escribir y escala. Los
textos centrados usan una caja de ancho fijo, así editar el texto no los corre.
El texto usa la fuente del sistema, o un archivo de `recursos/fuentes/` si el
gemelo lo indica (`estilo.fuente`).

### 13.2 Subtítulos

- **Importar `.srt`** (navegador): crea un texto con la plantilla Subtítulo por
  cada línea, en la capa T y el **idioma** elegidos. Tolera BOM, CRLF,
  etiquetas `<i>`/`<b>` y subtítulos que se pisan (el anterior termina donde
  empieza el siguiente).
- Una capa T **con idioma** es una pista de subtítulos: solo se ve al escuchar
  ese idioma y **no se dibuja en el video final**; el render la entrega como
  `.srt` (sección 16). Con "siempre visible" (sin idioma) el texto va quemado en
  el video para todos.

---

## 14. Audio

- **Mezcla**: todos los Elementos A, el sonido de los V no silenciados y Global,
  con volumen, paneo, fundidos y keyframes, más un limitador que evita la
  saturación.
- **Velocidad**: a velocidad constante el audio **conserva el tono** (WSOLA);
  en las rampas el tono sigue a la velocidad.
- **Medidores de nivel** por canal en el monitor (botón señal).
- **Bajar con la voz** (ducking), en un audio de música: busca dónde hay voz
  (las capas con idioma o, si no hay, el resto de los audios de los minutos),
  une frases cercanas y pone keyframes de volumen: baja 12 dB 6 fotogramas antes
  y vuelve en 12 fotogramas.
- **Sonoridad**: el panel de render mide los LUFS integrados (ITU-R BS.1770) y
  el pico del minuto o del capítulo. El render **normaliza a −14 LUFS**
  (YouTube) sin pasar de −1 dBFS de pico, cada pista de idioma por separado.
- **Reducción de ruido**: en el Taller (sección 9.5).

---

## 15. Idiomas

Modelo de doblaje: **pista común + diálogo por idioma**.

| Capa | Idioma | Suena / se ve en |
|---|---|---|
| Música, efectos, ambiente (A) | vacío (común) | Todos los idiomas |
| Diálogo (A) | `es`, `en`… | Solo ese idioma |
| Textos (T) | vacío | Todos, quemados en el video |
| Subtítulos (T) | `es`, `en`… | Solo ese idioma; `.srt` al renderizar |

- El idioma se asigna **por capa** del capítulo (botón en la cabecera de la
  pista); vale para los 24 minutos y para Global.
- El proyecto declara sus idiomas en ☰ Proyecto → Idiomas (por defecto `es`);
  el **primero es el principal**. No se puede quitar un idioma que usa algún
  capítulo, esté o no cargado.
- **Escucha** (monitor): elige qué idioma suena y qué subtítulos se ven en la
  vista previa; no toca el modelo.
- **Render**: un solo video, **una pista de audio por idioma** y **un `.srt` por
  idioma**.
- **Shorts**: el idioma principal, con su audio y sus subtítulos quemados.
- Cada idioma tiene su propia huella de audio: cambiar el diálogo en inglés no
  invalida lo renderizado en español.

---

## 16. Render y entregables

### 16.1 Panel de render

- **Minuto actual**, **rango I–O** (los minutos que cubre) o **capítulo completo**.
- **Perfil**: **Video 720p (YouTube)** o **Solo audio (.m4a)**.
- **Sonoridad −14 LUFS** (activado por defecto) y botones para **medir la
  sonoridad** del minuto o del capítulo.
- **Capítulos de YouTube**: muestra el texto para copiar en la descripción.
- **Entregables del capítulo**: lista de archivos con su estado (en disco o
  falta) y botón para abrir la carpeta.

Antes de renderizar se comprueba el espacio en disco.

### 16.2 Proceso

```
Capítulo:  [00✅][01✅][02🔴][03✅] … [23✅]
                        │ solo se renderiza el minuto 02
                        ▼
   video = minutos unidos SIN recodificar (con fotograma clave al inicio de cada uno)
   audio = una pasada del mezclador por idioma (normalizada)
```

- Cada minuto se renderiza a calidad final (Lanczos) desde los archivos reales y
  se guarda en `.cache/minutos/` con su **huella** en el nombre: un minuto cuya
  huella no cambió **no se vuelve a renderizar**.
- La **huella de video** de un minuto resume todo lo que cambia su imagen: sus
  Elementos, lo que entra desbordado, lo de Global que lo cruza, el estado de
  las capas, la firma de cada archivo fuente y el estándar. Los subtítulos de
  idioma no cuentan (no se dibujan en el video).
- El **estado de render** de cada minuto (sin render, desactualizado, al día)
  compara esa huella con la del último render y se ve en el mapa y el
  navegador.
- Codificación por software (`libx264`) o por hardware NVIDIA (NVENC) según el
  estándar del proyecto.

### 16.3 Archivos que se entregan

| Archivo | Contenido |
|---|---|
| `cap0001_completo_v002.mp4` | Video 720p con una pista de audio por idioma (etiquetada) |
| `cap0001_completo_v002.m4a` | Perfil solo audio: una pista por idioma |
| `cap0001_completo_v002_es.srt` | Subtítulos de cada idioma que tenga textos en capas T de ese idioma, con tiempos desde el inicio del rango |
| `cap0001_completo_v002.txt` | Capítulos de YouTube desde los marcadores del rango |

Cada render lleva una versión nueva (`_vNNN`) y queda registrado en
`_renders.json` aunque el usuario no guarde.

**Capítulos de YouTube**: una línea `M:SS Título` por marcador, con el nombre
del marcador (o "Parte N"). Si no hay marcador al comienzo se agrega
`0:00 Inicio`. Avisa si hay menos de 3 capítulos o alguno dura menos de 10 s
(reglas de YouTube).

---

## 17. Shorts verticales 9:16

Un Short **no es un video aparte**: es un **recorte vertical de un rango del
capítulo**, guardado como receta en `cap0001/shorts/`.

### 17.1 Geometría

```
LIENZO 16:9 · 1280×720
┌────────────────────────────────────────┐
│             ┌────────┐                 │
│             │VENTANA │ 405×720 (zoom 1)│
│             │  9:16  │                 │
│             └────────┘                 │
└────────────────────────────────────────┘
                  ▼
          SHORT · 720 × 1280
```

- La ventana ocupa toda la altura con **zoom 1** (405×720) y se mueve en
  horizontal (x entre 0 y 875; centrada por defecto).
- **Zoom** ≥ 1 achica la ventana para acercarse a la acción (queda centrada en
  vertical).
- **x** y **zoom** son **animables**: con keyframes, la ventana sigue la acción.
- El rango puede cruzar minutos, no capítulos. Dura hasta **3 minutos**.

### 17.2 Calidad

El Short **no recorta el video renderizado**: cada fotograma se **vuelve a
componer** a 720×1280 a través de la ventana, desde los archivos reales de las
Piezas (que conservan hasta 2560×1440). Los textos se dibujan nítidos a la nueva
escala. Audio y subtítulos: los del **idioma principal**, los subtítulos
**quemados**, sonoridad −14 LUFS.

### 17.3 Espacio Shorts

- **Lista** de Shorts del capítulo con su estado: sin render, **al día** o
  **desactualizado** (si cambió algo que el Short muestra u oye).
- **+ Nuevo**: con I–O marcados usa ese rango; si no, 30 s desde el cabezal.
- **Vista vertical** del Short en el cabezal y deslizador de tiempo dentro del
  Short. El monitor 16:9 de al lado dibuja la **ventana** del Short elegido,
  también mientras se arrastra.
- **Posición horizontal** y **zoom**: sin keyframes mueven la ventana fija; con
  keyframes ponen uno en el cabezal. **Keyframe aquí** fija el encuadre del
  cabezal; **Ventana fija** quita los keyframes.
- **Usar rango I–O**, **Ir al inicio**, **nombre**, **quitar**.
- **Renderizar** el Short elegido o **todos los pendientes**; se guardan como
  `…_vNNN.mp4` en `capNNNN/shorts/`, y la carpeta se abre con un botón.

Receta de un Short:

```json
{
  "id": "b71c4d",
  "nombre": "momento-clave",
  "tiempo": { "inicio": "min02_seg10f00", "duracion": "dur45s00" },
  "ventana": { "x": 437.5, "zoom": 1.0,
               "keyframes": { "x": [ { "f": 0, "valor": 437.5, "curva": "ease-in-out" },
                                     { "f": 240, "valor": 780 } ] } }
}
```

---

## 18. Proyecto, capítulos y mantenimiento

Menú **☰ Proyecto**:

- **Idiomas del proyecto**: códigos separados por coma; el primero es el
  principal.
- **Atajos de teclado**: redefinir cualquier acción (se guardan en
  `~/.config/editor/atajos.json`, solo las que se cambian).
- **Mantenimiento**: tamaño de cada parte del proyecto, **vaciar la caché**
  (se regenera sola), **vaciar la papelera** (con confirmación: después ya no
  se puede deshacer lo guardado antes) y **quitar los Brutos sin uso** (los que
  ninguna Pieza ni capítulo usa, cargado o no).

Antes de importar, hornear o renderizar se comprueba que quede espacio en
disco (con un margen de 500 MB).

Configuración del usuario en `~/.config/editor/`: proyectos recientes y
ajustes (`ajustes.json`), tamaños de paneles (`distribucion.json`) y atajos
(`atajos.json`). Los valores de fábrica están en `config/` del repositorio.

| Ajuste | Por defecto |
|---|---|
| Caché de fotogramas decodificados | 512 MB |
| Autosave | cada 120 s |
| Pasos de deshacer | 100 |
| Vista previa en vivo | 12 fps, JPEG 80 |
| Fotograma exacto | JPEG 90 |
| Trabajadores de fondo | 2 |
| Proyectos recientes | 10 |

---

## 19. Atajos y gestos

| Acción | Atajo |
|---|---|
| Reproducir / pausar | Espacio · L |
| Fotograma anterior / siguiente | ← → (en el Taller, fotograma nativo) |
| Segundo anterior / siguiente | Shift + ← → · J retrocede un segundo |
| Inicio del minuto · minuto anterior / siguiente | Inicio · RePág / AvPág |
| Entrada / salida | I / O |
| Dividir en el cabezal | S |
| Marcador | M |
| Herramientas | V selección · C cuchilla · B ripple · N roll · Y slip · U slide |
| Keyframe | K |
| Deshacer / rehacer | Ctrl+Z / Ctrl+Shift+Z · Ctrl+Y |
| Guardar | Ctrl+S |
| Copiar / pegar / duplicar | Ctrl+C / Ctrl+V / Ctrl+D |
| Quitar / quitar con ripple | Supr / Shift+Supr |
| Buscar | Ctrl+F |
| Zoom de la timeline | = / − |
| Mover 1 px / 10 px en el monitor | Alt + flechas / Alt + Shift + flechas |
| Deseleccionar | Esc |

Con el foco en un campo de texto solo funciona Ctrl+S.

| Dónde | Gesto | Acción |
|---|---|---|
| Regla de la timeline | Clic · arrastrar | Mover el cabezal (se pega a un marcador cercano) |
| Elemento en la timeline | Clic (Shift: sumar) · arrastrar cuerpo o borde | Seleccionar · la operación de la herramienta |
| Elemento en la timeline | Doble clic | Abrir su Pieza en el Taller |
| Audio en la timeline | Alt + arrastrar | Volumen |
| Timeline | Rueda (Ctrl: zoom) | Desplazar en los zooms de segundos y fotograma |
| Monitor | Clic · arrastrar | Seleccionar · mover, o la asa: escalar, girar, ancla (Shift: libre) |
| Mapa | Clic · doble clic · clic derecho en dos celdas | Ir · marcar listo · intercambiar minutos |
| Divisores | Arrastrar · doble clic | Tamaño · plegar |

---

## 20. Modos sin interfaz

```bash
python main.py                                   # interfaz: último proyecto o pantalla de inicio
python main.py RUTA                              # interfaz con ese proyecto
python main.py --nuevo RUTA                      # crear un proyecto y abrirlo
python main.py --escanear RUTA                   # leer el proyecto del disco y mostrar el informe
python main.py --render RUTA --capitulo 1 [--minutos 00-05] [--solo-audio]
python main.py --shorts RUTA --capitulo 1        # renderizar los Shorts que no están al día
python main.py --fotograma RUTA --capitulo 1 --tiempo 02:12.08 [--salida f.png]
```

- `--render` usa el mismo proceso que la interfaz: reutiliza los minutos al día,
  normaliza a −14 LUFS y escribe `.srt` y capítulos de YouTube.
- `--escanear` informa Elementos, Shorts, medios fuera de línea, gemelos
  faltantes, archivos fuera de su carpeta y no reconocidos.
- Todos respetan el bloqueo del proyecto; `--nivel-registro DEBUG` da detalle.

---

## 21. Arquitectura del código

### 21.1 Niveles

```
 N7  main.py                         punto de entrada único
 N6  editor/app/ui                   Flet: solo muestra y captura
 N5  editor/app                      Sesion, estado de la aplicación, controladores
 N4  editor/core/servicios           importar, hornear, vista previa, render, Shorts, guardar, análisis
     editor/core/tareas              cola de tareas de fondo
 N3  editor/core/comandos            ediciones con deshacer
     editor/core/proyecto_fs         disco: estructura, gemelos, diario, escáner, reconciliador
     editor/core/motor               decodificar, componer, efectos, texto, mezclar, codificar
 N2  editor/core/modelo              Proyecto → Capítulo → Minuto → Elemento
 N1  editor/core/tiempo              granularidad, nomenclatura
     editor/core/espacio             lienzo, transformaciones, geometría
 N0  editor/core/estandar            HD720-24
     editor/core/ajustes             ajustes de la aplicación
     editor/core/eventos             bus de eventos
     editor/core/utiles              interpolación, matemáticas, registro
```

Cada nivel importa solo niveles inferiores. Los tres módulos de N3 no se
conocen entre sí: lo que necesita varios (hornear = motor + disco + comando) lo
orquesta un servicio de N4. La interfaz nunca crea comandos del núcleo por su
cuenta sin pasar por la `Sesion`, y nunca toca el modelo directamente.

### 21.2 Archivos

```
main.py                    modos, arranque y cierre
config/                    estandar.json, ajustes.json, distribucion.json, atajos.json
editor/core/
  estandar.py ajustes.py eventos.py
  utiles/                  interpolacion (curvas y bezier), matematicas, registro
  tiempo/                  granularidad (fotograma ↔ min/seg/f), nomenclatura (nombres ↔ datos, IDs)
  espacio/                 lienzo (visibilidad, región, márgenes, ventana vertical), transform, geometria
  modelo/                  proyecto, capitulo, minuto, global_, composicion, elemento, capa, keyframe,
                           efecto, transicion, texto, plantillas_texto, marcador, short, bruto, pieza,
                           taller, referencias, errores
  comandos/                comando, compuesto, historial, estado_capitulo, operaciones, fabrica,
                           agregar/quitar/mover/recortar/dividir elemento, ripple, roll, slip, slide,
                           colocacion (rango, huecos, congelar), separar_audio, cambiar_propiedad,
                           transformar_elemento, agregar/quitar keyframe, agregar/quitar efecto,
                           cambiar_transicion, presets, capas (estado, marcadores, título, minutos),
                           mover_minuto, editar_short, taller, actualizar_fuente, proyecto (idiomas)
  proyecto_fs/             serializacion, estructura, gemelo, manifiestos, bloqueo, estado_disco,
                           automatico, diario, reconciliador, escaner, consultas, guion, autosave
  motor/                   motor_base, decodificador, codificador, cache_fotogramas, compositor,
                           texto, efectos/, conversion_fps, mezclador_audio, estiramiento (WSOLA)
  servicios/               fuentes, importacion, horneado, banco, miniaturas, forma_onda, huellas,
                           vista_previa, render, ensamblado, subtitulos, capitulos_youtube, shorts,
                           analisis (escenas, silencios, sincronía, movimiento, sonoridad, voz),
                           audio_procesado (ruido), guardado, mantenimiento
  tareas/cola.py           prioridades, instantáneas, cancelación
editor/app/
  aplicacion.py            arranque Flet, inicio ↔ proyecto, diálogos, cierre
  estado.py                Sesion (comandos, tareas, un capítulo en memoria) y EstadoApp
  controladores/           proyecto, medios, taller, timeline, reproduccion, render, creativo,
                           audio, shorts
  ui/                      ventana, divisor, distribucion, inicio, navegador, monitor, asas,
                           inspector, editor_curvas, mapa_capitulo, timeline, pistas_medios,
                           taller, cola_render, shorts, dialogos_proyecto, teclado, tema,
                           widgets/, recursos/temas/oscuro.json
```

Dependencias de Python (`requirements.txt`): `flet[desktop]`, `flet-video` y
`flet-audio` 1.0.2 (siempre la misma versión los cuatro paquetes de Flet), `av`
18.1.0, `numpy` 2.5.3, `opencv-python-headless` 5.0.0.93, `Pillow` 12.3.0.

### 21.3 Comandos

```
Controlador ── Sesion.ejecutar(comando) ──► Historial ──► comando.ejecutar(proyecto)
                  │ ErrorModelo / ValueError → aviso, nada cambia
                  ▼
             eventos: ElementoCambiado (minutos afectados), HistorialCambiado, ProyectoModificado
```

- `EdicionCapitulo` guarda copias de los Elementos que toca y deshacer las
  restaura; `EdicionEstadoCapitulo` hace lo mismo con capas, marcadores, Shorts
  y minutos.
- Los comandos de arrastre usan **valores absolutos** y una `clave_fusion`:
  pasos seguidos del mismo gesto se funden en uno.
- `ComandoCompuesto` agrupa varios comandos en un solo paso (presets,
  bajar con la voz, importar subtítulos).
- Los IDs de Elementos nuevos se reservan al crear el comando: rehacer
  recrea los mismos IDs.

### 21.4 Eventos

El núcleo avisa hacia arriba sin importar capas superiores:

| Evento | Lo publica | Reaccionan |
|---|---|---|
| `ProyectoAbierto` / `ProyectoCerrado` | proyecto | aplicación |
| `ProyectoModificado` / `HistorialCambiado` | historial | toda la ventana, barra (•) |
| `ProyectoGuardado` | guardado | barra, mapa |
| `CapituloCreado` | proyecto | navegador |
| `ElementoCambiado` (y `Agregado`, `Quitado`) | historial | timeline, monitor, inspector, mapa |
| `ShortCambiado` | historial, al cambiar un Short | espacio Shorts (se redibuja con `HistorialCambiado`) |
| `BrutoImportado`, `PiezaModificada`, `PiezaHorneada` | importación, Taller, horneado | navegador, Taller, timeline |
| `BancoListo` | banco de vista previa | monitor, timeline |
| `TareaProgreso` / `TareaTerminada` | cola de tareas | barra de tareas |
| `RenderTerminado` | render | panel de render, mapa |

### 21.5 Hilos y tareas

- El modelo **solo se modifica en el hilo de Flet**, siempre con comandos.
- Lo largo va a la **cola de tareas** (hilos de fondo) sobre **instantáneas**:
  `Capitulo.instantanea(inicio, fin)` copia solo lo que toca el rango.
- `Sesion.tarea(tarea, al_terminar)` devuelve el resultado al hilo de Flet; los
  eventos del bus también se pasan a ese hilo y los redibujados se agrupan (uno
  por cuadro).
- Una tarea con `clave` reemplaza a la anterior con la misma clave (el monitor
  siempre muestra el último fotograma pedido).

| Prioridad | Tareas |
|---|---|
| 1 | Monitor, visores, señal |
| 2 | Banco de lo visible, análisis |
| 3 | Pre-render del minuto actual, audio del transporte, horneado |
| 4 | Banco del resto |
| 5 | Pre-render del resto |
| 6 | Render final y Shorts |

### 21.6 Secuencias

**Abrir**: bloqueo → diario pendiente → `_proyecto.json` → Taller → capítulo →
limpieza de temporales → ¿autosave más reciente? → ventana.

**Importar → preparar → colocar**: copia y análisis (tarea) → Taller: tramos,
fps, método (comandos) → hornear (tarea) → copias actualizadas → banco (tarea)
→ `BancoListo` → colocar (comando). La vista previa lee el horneado hasta que
se guarde.

**Editar**: gesto → controlador → comando → eventos → timeline, monitor e
inspector se redibujan → la huella del minuto cambia → pre-render en cola.

**Guardar**: reconciliador (plan) → diario → materialización → renombres en
dos fases → gemelos y manifiestos → guion → `ProyectoGuardado`.

**Renderizar**: pedido (instantánea del capítulo) → minutos desactualizados →
audio por idioma → ensamblado → `.srt` y capítulos → registro en
`_renders.json` → `RenderTerminado`.

**Cerrar**: ¿cambios? → guardar, descartar o cancelar → detener tareas →
liberar decodificadores y bloqueo.

---

## 22. Reglas de integración

| Regla | Por qué |
|---|---|
| La interfaz y los servicios se refieren a los Elementos **por ID** | Deshacer restaura copias, no los mismos objetos |
| Las tareas de fondo nunca llaman a `proyecto.capitulo()` ni tocan el modelo | Cargar capítulos y ejecutar comandos solo ocurre en el hilo de Flet |
| Una tarea cuyo resultado edita el capítulo se envía con `del_capitulo=True` | Si el usuario cambió de capítulo, el resultado no se aplica al equivocado |
| Los renders y horneados se anotan con `proyecto_fs/automatico.py` | No dependen de que el usuario guarde; con el capítulo descargado se escribe en disco sin cargarlo |
| `Elemento.archivo` puede faltar o estar desactualizado | El motor siempre resuelve el archivo con `servicios/fuentes.py` |
| Solo un capítulo en memoria | Cambiar de capítulo exige guardar; lo no cargado siempre está guardado |
| Toda huella se calcula con la serialización canónica | Sin falsos "desactualizado" |
| Efectos y transiciones tienen **descriptor** (parámetros, rangos, opciones) | La interfaz arma sus controles sin conocer cada tipo |

Consultas del núcleo más usadas:

| Necesidad | Llamada |
|---|---|
| Qué se ve en f | `Capitulo.visuales_activos_en(f, idioma)` (ordenado de abajo hacia arriba) |
| Qué suena en f | `Capitulo.sonoros_activos_en(f, idioma)` |
| Transiciones en curso | `Capitulo.transiciones_activas(f)` |
| Fotograma de la fuente | `Elemento.fotograma_fuente(f)` (velocidad, rampas, reversa, congelado) |
| Transformación | `Elemento.transform_en(f)` |
| Lo que afecta a un minuto | `Capitulo.que_afecta_al_minuto(n)` |
| Ventana de un Short | `Short.rect_en(f)` |
| Imagen | `Compositor.componer(capitulo, f, tamaño, ventana, idioma)` |
| Audio | `Mezclador.mezclar(capitulo, inicio, fin, idioma)` |

---

## 23. Límites conocidos

| Límite | Detalle |
|---|---|
| Rendimiento medido | Vista previa en vivo ~218 fps a 256×144 con 3 capas; fotograma exacto ~130 ms a 1280×720 |
| Render del capítulo completo | El audio de los 24 minutos se mezcla en memoria (≈ 550 MB por idioma) |
| Shorts y marcadores | Quedan en su tiempo: no se corren con un ripple ni al intercambiar minutos |
| Ripple | Su alcance es el minuto (lo que se desborda pasa al siguiente) |
| Rampas de velocidad | El tono del audio sigue a la velocidad |
| Renders anteriores | Las versiones viejas y los Shorts renombrados no se borran solos |
| Codificación por hardware | Solo NVENC (NVIDIA); sin él, `libx264` por software |
| Plataforma | Solo Linux de escritorio; sin tests automatizados: `--escanear` y `--render` sirven de verificación |
