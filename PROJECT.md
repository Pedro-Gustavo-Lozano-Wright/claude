# PROJECT.md — Editor de video por capítulos y minutos

Documento maestro de arquitectura. Recoge el enfoque, las decisiones y las
épicas acordadas. Es la referencia única: si el código contradice este
documento, se corrige uno de los dos de forma explícita.

- **Estado:** planificación cerrada (revisión 3). Todavía no hay código funcional.
- **Plataforma:** solo Linux. Desarrollo y ejecución desde PyCharm.
- **Punto de partida:** los andamiajes vacíos `qwen_video_editor/` y
  `deep_video_editor/`, que se unifican en una sola arquitectura: `editor/`.
- **Modo de trabajo:** solo código. Sin tests ni pruebas automatizadas por ahora.
  Un único punto de entrada: `main.py`.

---

## Índice

0. [Cambios de las revisiones 2 y 3](#0-cambios-de-las-revisiones-2-y-3)
1. [Visión](#1-visión)
2. [Decisiones de base](#2-decisiones-de-base)
3. [Nomenclatura única](#3-nomenclatura-única)
4. [Estándar objetivo HD720-24](#4-estándar-objetivo-hd720-24)
5. [Paradigma: composiciones anidadas sobre una rejilla de tiempo](#5-paradigma-composiciones-anidadas-sobre-una-rejilla-de-tiempo)
6. [Sistema de tiempo y granularidad](#6-sistema-de-tiempo-y-granularidad)
7. [Sistema espacial](#7-sistema-espacial)
8. [El Elemento: bloque fundamental](#8-el-elemento-bloque-fundamental)
9. [Estructura del proyecto en disco](#9-estructura-del-proyecto-en-disco)
10. [Sincronización disco–modelo](#10-sincronización-discomodelo)
11. [Motor de composición, transparencias y audio](#11-motor-de-composición-transparencias-y-audio)
12. [Vista previa híbrida en 4 niveles](#12-vista-previa-híbrida-en-4-niveles)
13. [Render por minuto y ensamblado del capítulo](#13-render-por-minuto-y-ensamblado-del-capítulo)
14. [Flujo de dependencias](#14-flujo-de-dependencias)
15. [El main principal](#15-el-main-principal)
16. [Interfaz de usuario](#16-interfaz-de-usuario)
17. [Arquitectura del código](#17-arquitectura-del-código)
18. [Unificación de qwen y deep](#18-unificación-de-qwen-y-deep)
19. [Épicas en orden sistemático](#19-épicas-en-orden-sistemático)
20. [Especificaciones aspirables](#20-especificaciones-aspirables)
21. [Riesgos y decisiones abiertas](#21-riesgos-y-decisiones-abiertas)

---

## 0. Cambios de las revisiones 2 y 3

### Revisión 3: decisiones del usuario

| # | Decisión | Consecuencia | Sección |
|---|---|---|---|
| U1 | **24 fps** como único estándar | Fotograma del nombre siempre `f00`–`f23` | 4 |
| U2 | **Capítulo = exactamente 24 minutos** (24 bloques de 1 min) | 34 560 fotogramas fijos; sin duración variable; el tiempo vacío se renderiza en negro y silencio | 6.4 |
| U3 | **Capítulos del 1 al 1000** | Código de 4 dígitos: `cap0001`–`cap1000` | 3 |
| U4 | **Solo formato panorámico 16:9** (1280×720) | Un único lienzo | 4 |
| U5 | **Shorts verticales 9:16 como recorte** del 16:9, en su propia carpeta | Ventana vertical animable sobre el lienzo, render nítido a 720×1280 | 13.5 |
| U6 | **Solo Linux**, ejecución desde PyCharm | Se eliminan las consideraciones de Windows y macOS; dependencias de sistema documentadas | 15.4 |
| U7 | **Asas de 1 segundo** fijas | Sin configuración | 4.2 |
| U8 | **Elegir el fps correcto al recortar** | Interpretación de fps por Bruto y método de conversión por Pieza; el Taller trabaja en los fotogramas nativos de la fuente | 6.7 |

### Revisión 2: cabos sueltos

Cabos sueltos detectados en la revisión 1 y cómo quedan resueltos:

| # | Cabo suelto | Resolución | Sección |
|---|---|---|---|
| R1 | Sin punto de entrada definido | `main.py` único en la raíz, con modo interfaz y modo render sin interfaz | 15 |
| R2 | El núcleo no tenía cómo avisar hacia arriba sin importar la interfaz | **Bus de eventos** en `core/eventos.py`: flujo inverso sin dependencias inversas | 14.3 |
| R3 | Un mismo ID para la Pieza y su Elemento | IDs distintos; el gemelo apunta a la Pieza con `fuente.ref` | 3, 8.3 |
| R4 | Contradicción: "la carpeta solo contiene archivos con prefijo" frente a `minuto.json` | **Archivos de control con prefijo `_`** (`_minuto.json`, `_guion.txt`), que además quedan primeros al ordenar | 3.2 |
| R5 | ¿El minuto copia la Pieza o la referencia? | **Materialización**: el minuto guarda una copia; reutilizar una Pieza = varias copias sincronizadas por el índice de referencias | 5.5, 10.4 |
| R6 | Al cambiar una Pieza, nadie sabía qué minutos invalidar | **Índice de referencias** Pieza → Elementos → Minutos | 10.4 |
| R7 | Fuentes con otros fps (30, 60, variable) | **Las Piezas se hornean normalizadas**: 24 fps constantes, 48 kHz | 4.2 |
| R8 | Trim y slip sin material de sobra | **Asas**: la Pieza horneada guarda 1 s extra antes y después | 5.5 |
| R9 | Autosave provocaba renombres cada 2 minutos | Autosave = **instantánea** en `.autosave/`, sin renombres; solo "Guardar" reconcilia | 10.3 |
| R10 | Tareas en segundo plano leyendo el modelo mientras se edita | **Instantáneas inmutables** para los trabajadores; el modelo solo se modifica en el hilo principal | 14.4 |
| R11 | Ripple en un minuto desplazaba los 23 siguientes (renombres en cascada) | **Alcance del ripple**: "minuto" (por defecto) o "capítulo" | 6.5 |
| R12 | Solapamiento de Elementos en la misma capa | **Prohibido**, salvo durante una transición | 6.6 |
| R13 | Dónde se guardan las transiciones | En el gemelo del Elemento **entrante** (`transicion_entrada`) | 8.3 |
| R14 | Audio de los Elementos de video | Un Elemento V suena salvo que se silencie; el comando "separar audio" crea un Elemento A | 8.4 |
| R15 | Los textos no tienen archivo de medios | Un Elemento T es **solo su `.json`**: contenido y gemelo coinciden | 8.5 |
| R16 | Elementos más allá del final del capítulo | **Regla del marco temporal**, simétrica a la del lienzo | 6.4 |
| R17 | ¿Qué estándar manda: el global o el del proyecto? | `config/estandar.json` solo sirve para proyectos nuevos; cada proyecto guarda **su copia** en `_proyecto.json` | 4.3 |
| R18 | Hornear una Pieza no es una edición del modelo | Hornear es un **servicio** (produce un archivo) + un comando (actualiza la referencia) | 14.2 |
| R19 | Faltaba el mezclador de audio | `core/motor/mezclador_audio.py` | 11.6 |
| R20 | Medios desaparecidos | Estado **fuera de línea**: marco rojo en vista previa, aviso en el navegador | 8.6 |
| R21 | Fuentes tipográficas y LUT no viajaban con el proyecto | Carpeta `recursos/` dentro del proyecto | 9 |
| R22 | Estado de un minuto mezclaba lo manual y lo automático | Dos ejes: **estado de trabajo** (manual) y **estado de render** (automático) | 13.3 |
| R23 | qwen y deep conservados hasta el final generaban confusión | Se **eliminan en E0**; su mapeo queda documentado aquí | 18 |
| R24 | pydantic duplicaba el modelo | Modelo en `dataclasses`; serialización explícita en `proyecto_fs`; se retira pydantic | 2 |
| R25 | Prioridad entre tareas de fondo | Cola de tareas con prioridades: interacción > banco visible > pre-render > render final | 14.4 |

---

## 1. Visión

Un editor de video de escritorio en Python que organiza **todo por tiempo y
por contexto**:

- Un **proyecto** contiene hasta **1000 capítulos**. Cada capítulo mide
  **exactamente 24 minutos** y tiene una **carpeta por minuto**.
- Cada archivo vive en la carpeta del minuto donde empieza, y **su nombre
  indica el instante exacto en que aparece**. Con el programa apagado, los
  nombres ya cuentan la historia.
- Se edita en **secciones pequeñas**: un minuto a la vez para el trabajo fino,
  o el capítulo completo para el ritmo general.
- El render puede ser **de 1 minuto, de un rango o del capítulo completo**, y
  solo se re-renderizan los minutos que cambiaron.
- El material se prepara en un **Taller** (sandbox) antes de llegar a la
  timeline.
- Composición espacial en **píxeles sobre un lienzo 1280×720 (16:9)**, con
  capas apiladas y transparencias.
- Función extra: **Shorts verticales 9:16** recortados del capítulo 16:9, en su
  propia carpeta.

Referencia de experiencia: **CapCut / Clipchamp**, con mejor calidad de
exportación, precisión de fotograma y una organización de archivos legible por
humanos.

---

## 2. Decisiones de base

| # | Decisión | Motivo |
|---|---|---|
| D1 | **Interfaz en Flet** con vista previa híbrida | Diseño moderno y rápido de construir; sus límites de video se compensan con el banco de fotogramas y el pre-render |
| D2 | **`core/` en Python puro, sin librería de interfaz** | Desacople total; permite un modo sin interfaz y una futura interfaz PySide6 sin tocar el núcleo |
| D3 | **Una sola arquitectura unificada** con lo mejor de qwen y deep | Sin código duplicado ni dos caminos paralelos |
| D4 | **Motor PyAV** (sin MLT por ahora) | Instalación sencilla en todos los sistemas; `motor_base` permite agregar otros |
| D5 | **Tiempo interno en fotogramas enteros** del capítulo | Precisión exacta |
| D6 | **Espacio en píxeles del lienzo 1280×720**, origen (0,0) arriba a la izquierda | Intuitivo; otras resoluciones solo multiplican por un factor |
| D7 | **Nombre = historia (tiempo); gemelo `.json` = puesta en escena (espacio)** | Nombres cortos y siempre verdaderos; detalle completo y animable |
| D8 | **Todo cambio del modelo pasa por un Comando** | Deshacer y rehacer funcionan siempre |
| D9 | **El disco se reconcilia al guardar**, no en cada arrastre | Sin renombres masivos ni archivos bloqueados |
| D10 | **Español en todo el dominio** | Un concepto, un nombre, en todas partes |
| D11 | **Piezas horneadas, normalizadas y con asas** | Reproducción rápida, fps uniformes, margen para trim y slip |
| D12 | **Materialización**: cada minuto contiene copias reales de sus medios | La carpeta es autosuficiente y legible con el programa apagado |
| D13 | **Flujo inverso por eventos** | El núcleo nunca importa capas superiores |
| D14 | **Modelo en `dataclasses`**, serialización explícita | Un solo modelo, sin duplicar tipos |
| D15 | **Un único `main.py`** | Un solo punto de entrada para interfaz y render sin interfaz |
| D16 | **Solo código, sin tests** en esta etapa | Prioridad a construir la arquitectura completa |
| D17 | **Solo Linux** | Un solo sistema: rutas, renombres atómicos, codificación por hardware y dependencias de Linux |
| D18 | **Capítulo fijo de 24 minutos exactos** | Rejilla idéntica en todos los capítulos; render y ensamblado predecibles |
| D19 | **Un único lienzo 16:9**; el 9:16 es un recorte (Short) | Un solo flujo de edición; los verticales no duplican trabajo |
| D20 | **El Taller trabaja en el fps nativo de la fuente**; la conversión a 24 fps ocurre al hornear | Cortes exactos sobre los fotogramas reales; una sola frontera de normalización |

Alternativa futura documentada: interfaz **PySide6** sobre el mismo `core/`
si se necesita reproducción multicapa a 720p en tiempo real.

---

## 3. Nomenclatura única

### 3.1 Glosario

Regla: **cada concepto se llama igual en todas partes**. Sin tildes en código
y archivos; con tildes solo en la interfaz.

| Concepto | Carpeta | Archivos | Clave JSON | Clase | En pantalla |
|---|---|---|---|---|---|
| Proyecto | `MiSerie/` | `_proyecto.json` | `proyecto` | `Proyecto` | Proyecto |
| Capítulo | `cap0001/` | `_capitulo.json` | `capitulo` | `Capitulo` | Capítulo 1 |
| Minuto | `cap0001/min00/` | `_minuto.json`, `_guion.txt` | `minuto` | `Minuto` | Minuto 00 |
| Global | `cap0001/global/` | formato de Elemento | `global` | `Global` | Global |
| Bruto | `brutos/video\|audio\|imagen/` | `bru0001_nombre__id.ext` | `bruto` | `Bruto` | Bruto |
| Taller | `taller/` | — | `taller` | `Taller` | Taller |
| Pieza | `taller/pie0001_nombre__id/` | `_pieza.json`, `pie0001_nombre__id.ext` | `pieza` | `Pieza` | Pieza |
| Elemento | dentro de `minNN/` o `global/` | `minNN_segSSfFF_dur…_CAPA_nombre__id.ext` + gemelo `.json` | `elemento` | `Elemento` | Elemento |
| Capa | — | `V1`–`V9`, `A1`–`A9`, `T1`–`T9` | `capa` | `Capa` | V1, A1, T1 |
| Lienzo | — | — | `lienzo` | `Lienzo` | Lienzo |
| Keyframe | — | — | `keyframes` | `Keyframe` | Keyframe |
| Transición | — | — | `transicion_entrada` | `Transicion` | Transición |
| Efecto | — | — | `efectos` | `Efecto` | Efecto |
| Render | `cap0001/render/` | `cap0001_min00_v003.mp4` | `render` | `Render` | Render |
| Short | `cap0001/shorts/` | `min02_seg10f00_dur45s00_nombre__id.json` + `.mp4` | `short` | `Short` | Short |
| Ventana vertical | — | — | `ventana` | `VentanaVertical` | Encuadre 9:16 |
| Recursos | `recursos/fuentes\|luts/` | — | `recursos` | — | Recursos |

### 3.2 Reglas de archivos

1. **Archivos de Elemento**: empiezan con el prefijo de su carpeta
   (`cap0001/min02/` → `min02_…`). Excepción: en `global/` el prefijo expresa el
   minuto de inicio dentro del capítulo.
2. **Archivos de control**: empiezan con `_` (`_proyecto.json`,
   `_capitulo.json`, `_minuto.json`, `_guion.txt`, `_pieza.json`). Quedan
   primeros al ordenar y nunca se confunden con Elementos.
3. **Ceros a la izquierda en todo**: orden alfabético = orden cronológico.
4. **Minutos del 00 al 23, como un reloj**: `min02_seg12` es `02:12` en el
   reproductor.
5. **IDs**: 4 caracteres hexadecimales, **únicos en todo el proyecto**
   (Brutos, Piezas y Elementos comparten el mismo espacio de IDs). Nunca
   cambian.
6. **Nombre descriptivo**: minúsculas, números y guiones; máximo 32 caracteres.
7. **Capítulos**: `cap0001` a `cap1000`, siempre con 4 dígitos. En pantalla se
   muestra sin ceros: "Capítulo 1". El título libre va en `_capitulo.json`.

### 3.3 Gramática del nombre de un Elemento

```
min02_seg12f08_dur05s00_V2_puerta-abre__a3f9.mov
 │     │    │    │        │   │            │    │
 │     │    │    │        │   │            │    └ extensión (.mov si tiene alfa)
 │     │    │    │        │   │            └ ID del Elemento
 │     │    │    │        │   └ nombre descriptivo
 │     │    │    │        └ capa: V video/imagen · A audio · T texto (1–9)
 │     │    │    └ duración: segundos + fotogramas (dur01m05s00 si ≥ 1 min)
 │     │    └ fotograma de inicio (f00–f23)
 │     └ segundo de inicio (seg00–seg59)
 └ minuto de inicio (min00–min23)
```

Expresión regular de referencia:

```
^min(\d{2})_seg(\d{2})f(\d{2})_dur(?:(\d{2})m)?(\d{2})s(\d{2})_([VAT][1-9])_([a-z0-9-]{1,32})__([0-9a-f]{4})\.(\w+)$
```

Otros nombres:

| Objeto | Formato | Ejemplo |
|---|---|---|
| Bruto | `bruNNNN_nombre__id.ext` | `bru0001_toma-calle__7c21.mp4` |
| Pieza (carpeta y archivo) | `pieNNNN_nombre__id` | `pie0001_puerta-abre__5e1c.mov` |
| Render de un minuto | `capCCCC_minMM_vNNN.mp4` | `cap0001_min00_v003.mp4` |
| Render de un rango | `capCCCC_minMM-MM_vNNN.mp4` | `cap0001_min05-08_v001.mp4` |
| Render del capítulo | `capCCCC_completo_vNNN.mp4` | `cap0001_completo_v002.mp4` |
| Short (receta) | `minMM_segSSfFF_dur…_nombre__id.json` | `min02_seg10f00_dur45s00_momento-clave__b71c.json` |
| Short (render) | igual que la receta + `_vNNN.mp4` | `min02_seg10f00_dur45s00_momento-clave__b71c_v001.mp4` |

Un Short usa la misma gramática que un Elemento **sin el campo de capa**: el
nombre dice en qué instante del capítulo empieza y cuánto dura.

### 3.4 Convenciones de código

| Aspecto | Convención |
|---|---|
| Python | 3.12 o superior, con anotaciones de tipo |
| Módulos y funciones | `snake_case` en español sin tildes (`nomenclatura.py`, `evaluar()`) |
| Clases | `PascalCase` en español sin tildes (`Capitulo`, `Elemento`) |
| Constantes | `MAYUSCULAS` (`LIENZO_ANCHO`) |
| Modelo | `dataclasses` |
| Comandos | verbo + sustantivo (`MoverElemento`, `RecortarElemento`) |
| Eventos | sustantivo + participio (`ElementoCambiado`, `MinutoInvalidado`) |
| Imports | absolutos desde `editor.` y solo hacia capas inferiores (sección 14) |

---

## 4. Estándar objetivo HD720-24

### 4.1 Valores

| Parámetro | Valor |
|---|---|
| Lienzo | **1280 × 720 px, 16:9** (único formato de edición) |
| Origen | **(0, 0) = esquina superior izquierda**; X a la derecha, **Y hacia abajo** |
| Fotogramas por segundo | **24 fps constantes** (único) |
| Capítulo | **24 minutos exactos = 34 560 fotogramas** |
| Minuto | **1440 fotogramas** |
| Short (derivado) | 720 × 1280 px, 9:16, 24 fps |
| Píxel | Cuadrado |
| Color | sRGB / BT.709, 8 bits por canal |
| Composición interna | **RGBA con alfa premultiplicado** |
| Audio | 48 kHz, estéreo |
| Render final | H.264, CRF 18, yuv420p, AAC 192 kbps, `.mp4` |
| Banco de vista previa | 256 × 144 px, 10 fps; JPEG (opaco) o WebP (con alfa) |
| Vista previa pre-renderizada | 960 × 540, 24 fps, H.264 `ultrafast` |

**Regla del marco espacial:** lo que está dentro del lienzo se ve; lo que está
fuera existe, se guarda y se anima, pero no se muestra ni se renderiza.

### 4.2 Normalización de Piezas

Al hornear, toda Pieza queda en un formato uniforme:

| Parámetro | Valor |
|---|---|
| Fotogramas por segundo | 24 constantes, según la interpretación y el método elegidos (6.7) |
| Resolución | La original, limitada a **2560 × 1440** (margen para ampliar sin perder calidad) |
| Video opaco | H.264 alta calidad (CRF 14), `.mp4` |
| Video con alfa | ProRes 4444, `.mov` |
| Imagen | PNG (o WebP), sin horneado de video |
| Audio | WAV 48 kHz estéreo (dentro del video o suelto) |
| Asas | **1 s fijo** antes y después del tramo usado (24 fotogramas), si el Bruto lo permite |

Así el motor solo trabaja con fuentes de 24 fps y 48 kHz.

### 4.3 Dónde vive el estándar

- `editor/core/estandar.py`: la clase `Estandar` y los valores por defecto.
- `config/estandar.json`: valores para **proyectos nuevos**.
- `_proyecto.json`: **copia propia de cada proyecto**. Es la que manda al
  editar y renderizar ese proyecto.

---

## 5. Paradigma: composiciones anidadas sobre una rejilla de tiempo

### 5.1 Todo es una Composición

Una **Pieza**, un **Minuto** y un **Capítulo** son el mismo tipo de objeto:
una línea de tiempo con Elementos. Un solo motor, un solo compositor y un solo
historial para todos los niveles.

```
CAPÍTULO  (composición de 24 min exactos)
 ├── Global: música, narración, títulos generales
 └── MINUTO 00 … MINUTO 23  (ventanas de 60 s)
       └── Elementos (copias de Piezas horneadas)
             └── Pieza (composición corta del Taller)
                   └── Brutos (originales)
```

### 5.2 Los minutos son ventanas sobre un capítulo continuo

- El **capítulo es la línea de tiempo real y continua**.
- Cada **minuto es una ventana de 60 s** con su carpeta y su editor.
- Un Elemento **vive en la carpeta del minuto donde empieza** y puede
  **desbordarse** al siguiente, que lo muestra como referencia fantasma
  ("entra desde min02").
- Las transiciones que cruzan el límite de un minuto funcionan, porque el
  render de un minuto recorta la ventana del capítulo continuo.

### 5.3 Capas de trabajo (tiers)

```
DESARROLLO                                REPRODUCCIÓN
T0  BRUTOS    originales, intocables      T2  MINUTO     60 s, capas V/A/T
T1  TALLER    Piezas con mini-timeline    T3  CAPÍTULO   24 minutos + Global
              → horneado normalizado      T4  RENDER     1 min, rango o capítulo
```

### 5.4 Por qué el Taller va separado

| | Todo en la timeline | Taller separado |
|---|---|---|
| Timeline limpia | ❌ | ✅ |
| Reutilizar una Pieza en varios minutos | ❌ | ✅ |
| Operaciones pesadas | ❌ Se recalculan | ✅ Se hornean una vez |
| Experimentar sin riesgo | ❌ | ✅ |

Ida y vuelta: doble clic en un Elemento abre su Pieza en el Taller; al volver a
hornearla, todas sus copias se actualizan.

### 5.5 Materialización y asas

- Colocar una Pieza en un minuto **copia su archivo horneado** a la carpeta del
  minuto con el nombre del Elemento. La carpeta queda autosuficiente.
- La misma Pieza en tres minutos = tres copias. El **índice de referencias**
  (10.4) las mantiene sincronizadas cuando la Pieza se vuelve a hornear.
- Las Piezas son cortas, así que el costo en disco es acotado.
- Las **asas** (1 s extra a cada lado) permiten trim y slip sin volver al Taller.
- Imágenes y audio siguen la misma regla: se copian al minuto (o a `global/`).

---

## 6. Sistema de tiempo y granularidad

### 6.1 Jerarquía

```
Proyecto → Capítulo (24 min exactos) → Minuto (60 s) → Segundo (24 f) → Fotograma
   ≤ 1000        34 560 f                 1440 f
```

### 6.2 Reglas

- Internamente **todo es un número entero de fotogramas del capítulo**.
- Minuto, segundo, fotograma y nombre son **vistas calculadas**:
  `3176 = minuto 02, segundo 12, fotograma 08 = "min02_seg12f08"`.
- fps como fracción exacta (`Fraction(24, 1)`).
- Conversión **reversible**: nombre → fotograma → nombre devuelve el mismo texto.
- **Keyframes relativos al inicio del Elemento**, en fotogramas.

### 6.3 Tiempo de un Elemento

| Propiedad | Unidad | Significado |
|---|---|---|
| `inicio` | fotograma del capítulo | Sale del nombre |
| `duracion` | fotogramas | Sale del nombre |
| `fuente_entrada` | fotograma de la Pieza (24 fps) | Desde dónde se usa la Pieza (incluye las asas) |
| `velocidad` | factor | 1.0 normal; negativo = reversa |

Como las Piezas están normalizadas a 24 fps, `fuente_entrada` siempre está en
la misma unidad que el capítulo.

### 6.4 Regla del marco temporal

Simétrica a la del lienzo:

- El capítulo mide **siempre 24:00 exactos** (fotogramas 0 a 34 559). No hay
  duración variable.
- Las 24 carpetas `min00`–`min23` se crean siempre.
- Lo que un Elemento de `min23` desborde **más allá de 24:00** existe y se
  guarda, pero no se reproduce ni se renderiza; la timeline lo muestra
  atenuado.
- **El tiempo vacío** (ningún Elemento visible) se renderiza en **negro y
  silencio**. Así cada minuto dura siempre 1440 fotogramas y cada capítulo
  34 560.

### 6.5 Ediciones de tiempo

| Edición | Qué cambia | Qué queda fijo |
|---|---|---|
| Trim | Entrada o salida | Todo lo demás; queda un hueco |
| Ripple | Entrada o salida | Los siguientes se corren para no dejar hueco |
| Roll | El corte entre dos Elementos | La duración total |
| Slip | `fuente_entrada` | La posición en la timeline |
| Slide | La posición | El contenido; los vecinos se ajustan |

**Alcance del ripple** (R11):
- **Minuto** (por defecto): solo se desplazan los Elementos del mismo minuto.
  Si algo empuja más allá del segundo 59, se desborda al siguiente.
- **Capítulo**: se desplaza todo lo posterior en el capítulo. Provoca renombres
  y movimientos de carpeta en cascada al guardar; la interfaz lo avisa.

Ripple, Roll y Slide tocan varios Elementos: se implementan como **comandos
compuestos**.

### 6.6 Reglas de capa

- **Dos Elementos no se solapan en la misma capa**, salvo durante su transición.
- Orden de apilado: V1 (fondo) … V9, luego T1 … T9 (textos siempre encima).
- Las capas A no tienen orden visual; se mezclan todas.

### 6.7 Interpretación de fps al recortar (Taller)

Las fuentes llegan con fps distintos: 23,976 · 24 · 25 · 29,97 · 30 · 50 ·
59,94 · 60, o variables (típico de celulares). El proyecto es 24 fps fijo, así
que la conversión se decide **una sola vez, al hornear la Pieza**.

**Frontera de normalización:**

```
BRUTO (fps nativo)  ──►  TALLER (se recorta en fotogramas nativos)  ──►  HORNEADO  ──►  PIEZA (24 fps)
                                                                         ▲
                                                             aquí se convierte, una vez
```

**1. En el Bruto: fps detectado y fps interpretado**

| Campo | Significado |
|---|---|
| `fps_detectado` | Lo que declara el archivo (metadatos) |
| `fps_medido` | Calculado a partir de las marcas de tiempo reales de los fotogramas |
| `vfr` | `true` si el intervalo entre fotogramas varía (fps variable) |
| `fps_interpretado` | **El que elige el usuario**; por defecto, el medido |

Si el detectado y el medido no coinciden, o si hay `vfr`, el Taller lo avisa.
El usuario puede corregir el `fps_interpretado` (por ejemplo, un archivo que
dice 30 pero en realidad es 29,97).

**2. En el Taller: recorte en la rejilla nativa**

- La mini-timeline del Taller muestra la regla **en fotogramas del Bruto**,
  según su `fps_interpretado`.
- Entrada y salida se marcan sobre **fotogramas reales de la fuente**, sin
  redondeos.
- El timecode del Taller muestra el fps nativo; la timeline del minuto, siempre
  24.

**3. En la Pieza: método de conversión a 24 fps**

| Método | Qué hace | Duración | Movimiento | Uso típico |
|---|---|---|---|---|
| `tiempo` (por defecto) | Conserva el tiempo real: descarta o duplica fotogramas según su marca de tiempo | Igual | Puede haber saltos leves (30 → 24 descarta 1 de cada 5) | Uso general, fps variable |
| `conformar` | Usa cada fotograma de la fuente como un fotograma de 24 fps | Cambia | Perfecto | 23,976 → 24 (+0,1 %), 25 → 24 (−4 %) |
| `camara_lenta` | `conformar` aplicado a fuentes rápidas | Más larga | Perfecto y fluido | 60 → 24 = 2,5× más lento; 48 → 24 = 2× |
| `mezcla` | Fusiona fotogramas vecinos | Igual | Suave, con algo de desenfoque | 30 → 24 sin saltos |
| `interpolacion` | Genera fotogramas intermedios por flujo óptico | Igual | Suave; puede crear artefactos; lento | Tomas difíciles |

- Con `conformar` y `camara_lenta` el audio cambia de duración: se estira con
  corrección de tono o se silencia, a elección.
- Las **asas** de 1 s se calculan después de la conversión: siempre son 24
  fotogramas de la Pieza.
- La receta (`_pieza.json`) guarda el `fps_interpretado` y el método, así que
  volver a hornear da el mismo resultado.

---

## 7. Sistema espacial

### 7.1 Coordenadas

```
(0,0) ───────────────────────── X → ─────────────── (1280,0)
  │   ┌──────────────────────────────────────────┐
  │   │           LIENZO 1280 × 720              │
  Y   │     (200,150)                            │
  ↓   │        ┌────────────┐                    │
  │   │        │ Elemento   │ ← ancla en (0,0)   │
  │   │        └────────────┘   de sí mismo      │
  │   └──────────────────────────────────────────┘ ┌────┐
(0,720)                                   (1280,720)│    │ ← fuera: existe,
                                                    └────┘   no se ve
```

### 7.2 Propiedades espaciales

| Propiedad | Unidad | Por defecto | Significado |
|---|---|---|---|
| `x`, `y` | px del lienzo | `0, 0` | Dónde cae el ancla |
| `ancla_x`, `ancla_y` | px del Elemento | `0, 0` | Punto de colocación, giro y escala |
| `ancho`, `alto` | px | tamaño original | Solo lectura |
| `escala_x`, `escala_y` | factor | `1.0` | Negativo = espejo |
| `rotacion` | grados | `0` | Sentido horario |
| `recorte` | px (izq, arr, der, abj) | `0,0,0,0` | Antes de colocar |
| `opacidad` | 0.0–1.0 | `1.0` | |
| `mezcla` | modo | `normal` | normal, multiplicar, pantalla, superponer, sumar |
| `ajuste_inicial` | modo | `original` | original, encajar, llenar, estirar (solo al colocar) |

- Con el ancla por defecto, `x, y` es la esquina superior izquierda.
- Al mover el ancla, el editor compensa `x, y` para que el Elemento no salte.
- Coordenadas negativas y mayores que el lienzo permitidas.
- **Todas las propiedades son animables.**

### 7.3 Cálculo

```
M = Trasladar(x, y) · Rotar(rotacion) · Escalar(escala_x, escala_y) · Trasladar(-ancla_x, -ancla_y)
```

1. Rectángulo transformado (4 esquinas).
2. **Descarte** si no toca el lienzo: ni se decodifica.
3. **Región de interés**: intersección con el lienzo.
4. `cv2.warpAffine` solo sobre esa región.
5. Mezcla con opacidad y modo.

Para otra resolución se multiplica la matriz por un factor. Lo que se ve es lo
que se exporta.

---

## 8. El Elemento: bloque fundamental

**Una ventana de tiempo sobre un archivo, colocada en el lienzo y en la
timeline, cuyas propiedades son parámetros animables.**

### 8.1 Dimensiones

| Dimensión | Contenido |
|---|---|
| Identidad | `id`, nombre, capa, estado (activo, bloqueado, silenciado) |
| Fuente | Pieza de origen (`fuente.ref`) y archivo materializado |
| Tiempo | `inicio`, `duracion`, `fuente_entrada`, `velocidad` |
| Espacio | Sección 7.2 |
| Apariencia | Pila ordenada de efectos |
| Audio | `volumen`, `paneo`, `silenciado`, fundidos |
| Animación | Keyframes sobre cualquier parámetro numérico |
| Relaciones | Capa, `transicion_entrada`, desborde |

### 8.2 Evaluación

```
elemento.evaluar(fotograma N)
  1. ¿Activo en N (y dentro del marco temporal)?   → si no, nada
  2. ¿Toca el lienzo?                               → si no, nada
  3. N → fotograma de la fuente                     (fuente_entrada, velocidad)
  4. Fotograma al motor                             (PyAV + caché)
  5. Parámetros en N                                (keyframes interpolados)
  6. Efectos en orden
  7. Imagen RGBA + matriz                           → compositor
```

Monitor, miniaturas, vista previa y render usan este mismo proceso.

### 8.3 Archivo gemelo

```
min02_seg12f08_dur05s00_V2_puerta-abre__a3f9.mov    ← contenido
min02_seg12f08_dur05s00_V2_puerta-abre__a3f9.json   ← gemelo
```

```json
{
  "id": "a3f9",
  "fuente": { "tipo": "pieza", "ref": "5e1c", "version": 3 },
  "tiempo": {
    "inicio": "min02_seg12f08",
    "duracion": "dur05s00",
    "fuente_entrada": 24,
    "velocidad": 1.0
  },
  "espacio": {
    "x": 200, "y": 150,
    "ancla_x": 0, "ancla_y": 0,
    "escala_x": 1.0, "escala_y": 1.0,
    "rotacion": 0,
    "recorte": [0, 0, 0, 0],
    "opacidad": 1.0,
    "mezcla": "normal"
  },
  "keyframes": {
    "x": [
      { "f": 0,  "valor": -400, "curva": "ease-out" },
      { "f": 24, "valor": 200 }
    ]
  },
  "efectos": [],
  "transicion_entrada": { "tipo": "fundido", "duracion": 12 },
  "audio": { "volumen": 1.0, "paneo": 0.0, "silenciado": false },
  "estado": { "activo": true, "bloqueado": false }
}
```

- `fuente_entrada: 24` = empieza tras el segundo de asa inicial.
- `fuente.version` permite detectar copias desactualizadas de una Pieza.
- `transicion_entrada` va en el Elemento entrante; su duración es el solape
  permitido con el anterior en la misma capa.

### 8.4 Audio de los Elementos de video

- Un Elemento V con audio **suena** salvo que esté silenciado.
- **Separar audio** crea un Elemento A que referencia la misma Pieza y silencia
  el V. Ambos quedan independientes.

### 8.5 Elementos de texto

Un Elemento T **no tiene archivo de medios**: su `.json` es a la vez contenido y
gemelo:

```
min02_seg14f00_dur03s00_T1_titulo-capitulo__d4e2.json
```

Añade al gemelo la sección `texto`: contenido, fuente (de `recursos/fuentes/`),
tamaño, color, contorno, sombra, alineación y animación de entrada y salida.

### 8.6 Medios fuera de línea

Si falta el archivo de un Elemento:
- En la vista previa se muestra un **marco rojo** con su nombre.
- El navegador marca el minuto con un aviso.
- Si la Pieza de origen existe, se ofrece **rematerializar** la copia.
- El render se bloquea hasta resolverlo (o se renderiza con el marco, a elección).

### 8.7 Reparto de la información

| Dónde | Qué guarda |
|---|---|
| Carpeta | Capítulo y minuto |
| Nombre | Inicio, duración, capa, nombre, ID: **la historia** |
| Gemelo `.json` | Espacio, keyframes, efectos, transición, audio: **la puesta en escena** |
| `_minuto.json` | Estado de trabajo, notas, huella y último render |
| `_guion.txt` | Reflejo legible generado al guardar; nunca se lee |

La posición espacial **no va en el nombre**: tiene muchas dimensiones, suele
estar animada y cambia constantemente.

Ejemplo de `_guion.txt`:

```
MINUTO 02 · cap0001 · lienzo 1280×720 · 24 fps
───────────────────────────────────────────────────────────────────
02:00.00  V1  ciudad-amanece   12s08  pos (0,0)       esc 1.00  pantalla completa
02:12.08  V2  puerta-abre       5s00  pos (-400,150)→(200,150)  entra desde izquierda
02:14.00  T1  titulo-capitulo   3s00  pos (440,600)             texto
02:17.08  A1  dialogo-juan     40s00  —               vol 100 %
```

---

## 9. Estructura del proyecto en disco

```
MiSerie/                                    ← PROYECTO
├── _proyecto.json                          estándar propio, capítulos, contador de IDs
├── brutos/                                 T0 · originales, nunca se modifican
│   ├── video/   bru0001_toma-calle__7c21.mp4
│   ├── audio/   bru0002_entrevista__91be.wav
│   └── imagen/  bru0003_logo__0f3a.png
├── taller/                                 T1 · sandbox
│   └── pie0001_puerta-abre__5e1c/
│       ├── _pieza.json                     receta + versión + referencias
│       └── pie0001_puerta-abre__5e1c.mov   horneado normalizado (.mp4 si es opaco)
├── recursos/
│   ├── fuentes/                            .ttf / .otf usados por los textos
│   └── luts/                               .cube
├── cap0001/                                  ← CAPÍTULO
│   ├── _capitulo.json                      título, duración, registro de renders
│   ├── global/
│   │   ├── min00_seg00f00_dur24m00s00_A1_musica-tema__c810.wav
│   │   └── min00_seg00f00_dur24m00s00_A1_musica-tema__c810.json
│   ├── min00/                              ← MINUTO 00:00–00:59
│   │   ├── _minuto.json
│   │   ├── _guion.txt
│   │   ├── min00_seg00f00_dur12s08_V1_ciudad-amanece__4b7e.mp4
│   │   ├── min00_seg00f00_dur12s08_V1_ciudad-amanece__4b7e.json
│   │   ├── min00_seg12f08_dur05s00_V2_puerta-abre__a3f9.mov
│   │   ├── min00_seg12f08_dur05s00_V2_puerta-abre__a3f9.json
│   │   └── min00_seg14f00_dur03s00_T1_titulo-capitulo__d4e2.json
│   ├── min01/ … min23/
│   ├── render/
│   │   ├── cap0001_min00_v003.mp4
│   │   └── cap0001_completo_v002.mp4
│   └── shorts/                             ← recortes verticales 9:16
│       ├── min02_seg10f00_dur45s00_momento-clave__b71c.json       receta
│       └── min02_seg10f00_dur45s00_momento-clave__b71c_v001.mp4   720×1280
├── cap0002/ … cap1000/
├── .diario/                                operaciones de disco pendientes
├── .autosave/                              instantáneas del modelo
└── .cache/                                 BORRABLE: bancos, pre-renders, ondas, audio de vista previa
```

Importar un archivo **lo copia a `brutos/`** (el proyecto es autosuficiente).

---

## 10. Sincronización disco–modelo

**Principio:** el modelo en memoria es la verdad mientras se edita. Al guardar,
el disco pasa a ser su reflejo legible. Con el programa apagado, el disco
cuenta la historia completa.

### 10.1 Problemas y soluciones

| Problema | Solución |
|---|---|
| Renombrar en cada arrastre | Se reconcilia **al guardar** |
| Elemento que cambia de minuto | El reconciliador **mueve** los archivos de carpeta, no solo los renombra |
| Renombre atómico | En Linux, `os.rename` dentro del mismo sistema de archivos es atómico; el diario cubre las secuencias de varias operaciones |
| Decodificador con el archivo abierto | Linux permite renombrar archivos abiertos; aun así se liberan los decodificadores antes de reconciliar para no leer rutas viejas |
| Corte a mitad de operación | **Diario** en `.diario/`: plan escrito antes de ejecutar; al abrir se completa o se revierte |
| Deshacer | Solo cambia el modelo; el siguiente guardado reconcilia |
| Se pierde un gemelo | El **escáner** rescata tiempo y capa del nombre; espacio por defecto |
| Renombre manual | El ID permite reconocer el archivo |
| Mayúsculas y minúsculas | Linux las distingue: todos los nombres generados van en minúsculas |

### 10.2 Componentes

- **`estructura`**: crea proyecto, capítulos y `min00`–`min23`.
- **`gemelo`**: lee y escribe el `.json` de cada Elemento.
- **`diario`**: registra y ejecuta operaciones atómicas (copiar, mover, renombrar, borrar).
- **`reconciliador`**: compara modelo y disco, genera el plan y lo pasa al diario.
  Contenido y gemelo siempre juntos.
- **`escaner`**: reconstruye el modelo leyendo carpetas, nombres y gemelos.
- **`guion`**: genera `_guion.txt`.

### 10.3 Guardar frente a autosave

| | Guardar | Autosave |
|---|---|---|
| Cuándo | El usuario lo pide | Cada 120 s si hay cambios |
| Qué escribe | Renombres, movimientos, gemelos, manifiestos, guion | Una **instantánea** del modelo en `.autosave/` |
| Renombra archivos | ✅ | ❌ |
| Al abrir el proyecto | — | Si la instantánea es más reciente que el disco, se ofrece restaurarla |

### 10.4 Índice de referencias

El Proyecto mantiene en memoria (y reconstruye al abrir):

```
Bruto  → Piezas que lo usan
Pieza  → Elementos que son copias suyas
Elemento → Minuto donde vive (y minutos donde se desborda)
```

Usos:
- **Volver a hornear una Pieza** → se actualizan todas sus copias y se invalidan
  sus minutos.
- **Borrar un Bruto o una Pieza** → se avisa qué depende de ellos.
- **Huella de un minuto** → sabe qué Elementos le afectan.

---

## 11. Motor de composición, transparencias y audio

### 11.1 Apilado

Mezcla "sobre" con alfa premultiplicado:

```
resultado = frente + fondo × (1 − alfa_frente)
```

Orden: V1 … V9, luego T1 … T9, más los Elementos desbordados del minuto
anterior y los de `global/`.

### 11.2 Formatos con transparencia

| Formato | ¿Alfa? | Nota |
|---|---|---|
| PNG, WebP, GIF | ✅ | Imágenes |
| ProRes 4444 `.mov` | ✅ | **Formato de las Piezas con alfa** |
| QuickTime Animation / PNG en `.mov` | ✅ | Sin pérdida, pesado |
| VP9 `.webm` | ⚠️ | Solo con libvpx; al hornear se convierte a ProRes 4444 |
| MP4 H.264 / H.265 | ❌ | Opaco |

Sin alfa de origen, la transparencia se crea en el Taller (croma, máscaras,
recortes) y se hornea.

### 11.3 Librerías

| Librería | Uso |
|---|---|
| PyAV | Decodificar y codificar video y audio |
| Pillow | Imágenes, texto con fuentes TTF |
| OpenCV | `warpAffine`, escalado, color, croma |
| numpy | Mezcla, opacidad, modos de mezcla, audio |
| numba (opcional) | Acelerar bucles de píxeles |
| moderngl (futuro) | Composición por GPU |

Interpolación: `INTER_AREA` para reducir, `INTER_LINEAR` al arrastrar,
`INTER_CUBIC` / `INTER_LANCZOS4` para ampliar y para el render final.

### 11.4 Optimizaciones

- Descarte fuera del lienzo y fuera del marco temporal.
- Región de interés.
- Caché de imágenes fijas transformadas.
- Caché LRU de fotogramas decodificados (512 MB por defecto).
- Decodificar al tamaño necesario.

### 11.5 Escalabilidad estimada

| Escenario | Límite práctico estimado |
|---|---|
| Imágenes fijas | Decenas de capas |
| Video 720p por capa | ~5–8 capas en vista previa a 720p |
| Vista previa al 20 % | ~10–15 capas a 10 fps |
| Render final | Sin límite; solo tarda más |

Estimaciones a confirmar con el propio programa durante E7.

### 11.6 Mezclador de audio

- Suma todos los Elementos A, el audio de los V no silenciados y `global/`.
- Aplica volumen, paneo, fundidos y keyframes de volumen.
- Salidas: audio de vista previa del minuto o del capítulo (en `.cache/`) y
  audio final del capítulo en una sola pasada (sección 13).
- Limitador suave para evitar saturación.

---

## 12. Vista previa híbrida en 4 niveles

```
                       ┌──────────────────────────────────────┐
  AL IMPORTAR ────────►│ NIVEL 0: BANCO DE FOTOGRAMAS          │
                       │ 256×144 · 10 fps · JPEG / WebP alfa  │
                       │ + tira de miniaturas + forma de onda │
                       └──────────────┬───────────────────────┘
          ┌─────────────────┬─────────┴────────┬───────────────────┐
          ▼                 ▼                  ▼                   ▼
   SCRUBBING         EDITANDO + PLAY     PLAY FLUIDO          EN PAUSA
   Nivel 1           Nivel 2             Nivel 3              Nivel 4
   imagen del banco  composición en      pre-render del       fotograma exacto
   < 50 ms           vivo · 10–15 fps    minuto · 24 fps      desde la copia
                     + audio             control Video        ~150–300 ms
```

### 12.1 Nivel 0 — Banco

```
.cache/banco/<id>/
├── f000000.jpg …      256×144, 10 fps (WebP si hay alfa)
├── _indice.json       fotograma del banco ↔ fotograma de la fuente + firma del archivo
├── tira.jpg           miniaturas para la timeline
└── onda.json          picos de audio
```

Se genera en segundo plano para cada Pieza horneada. La **firma** (tamaño +
fecha de modificación) invalida el banco si el archivo cambia.

### 12.2 Nivel 1 — Scrubbing
Imagen del banco más cercana, sin composición.

### 12.3 Nivel 2 — Composición en vivo
Cada tic (10–15 por segundo): Elementos activos → banco → transform → mezcla →
JPEG → `ft.Image`.

### 12.4 Nivel 3 — Pre-render por minuto
- **Huella** del minuto (13.2). Si cambió, se re-renderiza en segundo plano a
  960×540, 24 fps, H.264 `ultrafast`.
- Se reproduce con el control Video de Flet como **lista de reproducción de
  minutos**. Al cruzar de minuto puede haber un micro-corte; si molesta, se une
  el rango en un solo archivo sin recodificar.
- Mapa del capítulo: **verde** listo, **rojo** pendiente (se usa el nivel 2).

### 12.5 Nivel 4 — Fotograma exacto
Decodifica de la copia materializada a resolución completa y compone al tamaño
real del monitor; JPEG calidad 90.

### 12.6 Audio como reloj maestro
El nivel 2 consulta la posición del audio de vista previa en cada tic y muestra
la imagen de ese instante; si se retrasa, **salta fotogramas**.

---

## 13. Render por minuto y ensamblado del capítulo

### 13.1 Proceso

```
Capítulo:  [00✅][01✅][02🔴][03✅] … [23✅]
                        │  solo se re-renderiza el minuto 02
                        ▼
   Video del capítulo = unir minutos SIN recodificar
   Audio del capítulo = una sola pasada del mezclador
   Entregable        = video unido + audio
```

- **Render de un minuto**: recorta la ventana del capítulo continuo (incluye
  desbordes y `global/`), a calidad final, desde las copias materializadas.
- **Fotograma clave al inicio** de cada minuto y parámetros de codificación
  idénticos, para unir sin recodificar.
- Entregables: un minuto, un rango o el capítulo; versionados `_vNNN`.

### 13.2 Huella de un minuto

Hash de:
- Todos los Elementos del minuto (gemelo completo + firma del archivo).
- Los Elementos del minuto anterior que se desbordan en él.
- Los Elementos de `global/` que lo cruzan.
- El estándar del proyecto.

### 13.3 Estados de un minuto

| Eje | Valores | Quién lo cambia |
|---|---|---|
| **Trabajo** | vacío · en progreso · listo | vacío es automático; el resto lo marca el usuario |
| **Render** | sin render · desactualizado · al día | automático, comparando la huella con la del último render |

Se guardan en `_minuto.json`, así que sobreviven al cierre del programa.

### 13.4 Calidad

1. Render desde las copias materializadas (normalizadas a partir de los originales), nunca desde el banco.
2. Escalado Lanczos.
3. CRF 16–18.
4. Opción H.265 y 10 bits.
5. Codificación por hardware en Linux si existe: **VAAPI** (Intel/AMD) o
   **NVENC** (NVIDIA); si no, `libx264` por software.
6. Sin marca de agua ni nube.

### 13.5 Shorts verticales 9:16

Un Short **no es un video aparte**: es un **recorte vertical del capítulo
16:9**, en un rango de tiempo, guardado en `cap0001/shorts/`.

**Geometría**

```
LIENZO 16:9 · 1280×720
┌──────────────────────────────────────────────┐
│              ┌─────────┐                     │
│              │ VENTANA │                     │
│              │  9:16   │  405 × 720 px       │
│              │         │  del lienzo         │
│              │ x = 437 │                     │
│              └─────────┘                     │
└──────────────────────────────────────────────┘
                    │
                    ▼
            SHORT · 720 × 1280
```

- La ventana ocupa **toda la altura** del lienzo (720 px) y **405 px de
  ancho** (720 × 9/16).
- Solo se mueve en horizontal: `x` entre 0 y 875. Por defecto, centrada
  (`x = 437`).
- `x` es **animable con keyframes**, para seguir la acción (reencuadre).
- Opcional: `zoom` ≥ 1.0 para una ventana más pequeña (se acerca a la acción),
  también animable.

**Calidad: por qué no se recorta el video ya renderizado**

Recortar 405×720 del render a 720p y ampliarlo a 720×1280 lo agranda 1,78
veces y se ve borroso. En su lugar, el Short **se vuelve a componer**:

1. La matriz del compositor se multiplica por `1280 / 720 = 16/9`.
2. Solo se compone la **región de la ventana** (región de interés), no el
   lienzo completo.
3. Los Elementos se toman de las copias materializadas, que conservan hasta
   2560×1440, y los textos se dibujan nítidos a la nueva escala.

Resultado: un Short de 720×1280 con el detalle real de las fuentes, no una
ampliación.

**Receta (`.json`)**

```json
{
  "id": "b71c",
  "capitulo": "cap0001",
  "tiempo": { "inicio": "min02_seg10f00", "duracion": "dur45s00" },
  "ventana": {
    "x": 437,
    "zoom": 1.0,
    "keyframes": {
      "x": [
        { "f": 0,   "valor": 437, "curva": "ease-in-out" },
        { "f": 240, "valor": 780 }
      ]
    }
  },
  "audio": "capitulo",
  "ultimo_render": { "version": 1, "huella": "…" }
}
```

**Reglas**

- El rango puede cruzar minutos, pero **no capítulos**.
- El audio es el del capítulo en ese rango.
- El nombre sigue la gramática del tiempo: dice dónde empieza y cuánto dura.
- Si cambia algún minuto que el Short cruza, su render queda **desactualizado**
  (misma lógica de huellas).
- El monitor muestra una **guía 9:16** sobre el lienzo para colocar la ventana.

---

## 14. Flujo de dependencias

### 14.1 Niveles

```
 N7  main.py                         punto de entrada único
 N6  editor/app/ui                   Flet: solo muestra y captura
 N5  editor/app                      estado, controladores
 N4  editor/core/servicios           orquestación: importar, hornear, pre-render,
     editor/core/tareas              render, autosave · cola de tareas de fondo
 N3  editor/core/comandos            ediciones con deshacer
     editor/core/proyecto_fs         disco: estructura, gemelos, diario, escáner
     editor/core/motor               decodificar, componer, mezclar, codificar
 N2  editor/core/modelo              Proyecto → Capítulo → Minuto → Elemento
 N1  editor/core/tiempo              granularidad, nomenclatura
     editor/core/espacio             lienzo, transform, geometría
 N0  editor/core/estandar            HD720-24
     editor/core/eventos             bus de eventos
     editor/core/utiles              interpolación, matemáticas, registro
```

### 14.2 Flujo directo: qué puede importar cada nivel

| Módulo | Puede importar | Nunca importa |
|---|---|---|
| `estandar`, `eventos`, `utiles` | biblioteca estándar | nada del proyecto |
| `tiempo`, `espacio` | N0 | modelo y superiores |
| `modelo` | N0, N1 | comandos, disco, motor |
| `comandos` | N0–N2 | disco, motor, servicios |
| `proyecto_fs` | N0–N2 | comandos, motor |
| `motor` | N0–N2 | comandos, disco |
| `servicios`, `tareas` | N0–N3 | app, ui |
| `app` | N0–N4 | ui |
| `ui` | `app` y los tipos de N0–N2 para mostrarlos | comandos directamente |
| `main.py` | todo | — |

Los tres módulos de N3 **no se conocen entre sí**. Cuando una operación
necesita varios (por ejemplo hornear: motor + disco + comando), la orquesta un
**servicio** en N4.

### 14.3 Flujo inverso: eventos

El núcleo necesita avisar hacia arriba (un render terminó, un minuto quedó
desactualizado) sin importar capas superiores. Para eso existe
`core/eventos.py`:

```
N3/N4 publica ──► BusEventos (N0) ──► N5 suscrito ──► actualiza la UI
```

Eventos principales:

| Evento | Lo publica | Reaccionan |
|---|---|---|
| `ElementoCambiado` | historial (tras un comando) | timeline, inspector, monitor, huella |
| `MinutoInvalidado` | servicio de huellas | mapa del capítulo, planificador de pre-render |
| `PiezaHorneada` | servicio de horneado | índice de referencias, banco |
| `BancoListo` | servicio de banco | timeline (miniaturas), monitor |
| `RenderProgreso` / `RenderTerminado` | servicio de render | cola de render, mapa |
| `ProyectoGuardado` | servicio de guardado | barra de estado |
| `MedioFueraDeLinea` | escáner / motor | navegador, monitor |

### 14.4 Hilos y tareas

- **El modelo solo se modifica en el hilo principal**, siempre mediante comandos.
- Las tareas de fondo trabajan sobre **instantáneas inmutables** (copia del
  minuto y su huella). Si la huella cambió al terminar, el resultado se descarta.
- Los trabajadores **nunca tocan la interfaz**: publican eventos; `app` los
  pasa al hilo de Flet.
- Cola con prioridades:

| Prioridad | Tarea |
|---|---|
| 1 | Fotograma del monitor (niveles 1, 2, 4) |
| 2 | Banco de las Piezas visibles |
| 3 | Pre-render del minuto actual y vecinos |
| 4 | Banco del resto |
| 5 | Pre-render del resto del capítulo |
| 6 | Render final (cuando el usuario lo pide sube a prioridad 3) |

### 14.5 Ciclo completo de una edición

```
Usuario arrastra un Elemento
  → ui/timeline captura el gesto
  → app/controladores/timeline crea MoverElemento
  → core/comandos/historial ejecuta y guarda para deshacer
  → modelo cambia
  → eventos: ElementoCambiado
       ├─ app/estado → ui redibuja timeline e inspector
       ├─ servicio de huellas → MinutoInvalidado → mapa en rojo
       │                                          → tareas: pre-render (prioridad 3)
       └─ app/estado → proyecto "sin guardar"
  → (Guardar) servicio de guardado → reconciliador → diario → disco
```

---

## 15. El main principal

Un solo archivo en la raíz: **`main.py`**.

### 15.1 Modos

```
python main.py                               abre la interfaz (último proyecto o pantalla de inicio)
python main.py RUTA_PROYECTO                 abre la interfaz con ese proyecto
python main.py --nuevo RUTA_PROYECTO         crea un proyecto y lo abre
python main.py --render RUTA_PROYECTO --capitulo 1 [--minutos 00-05]
                                             renderiza sin interfaz
python main.py --escanear RUTA_PROYECTO      reconstruye el modelo desde el disco y reporta
python main.py --shorts RUTA_PROYECTO --capitulo 1
                                             renderiza los Shorts desactualizados del capítulo
```

### 15.2 Arranque

```
main.py
  1. Leer argumentos y config/ajustes.json
  2. Configurar el registro (utiles/registro)
  3. Crear el BusEventos
  4. Abrir o crear el Proyecto (proyecto_fs: escaner / estructura)
     └─ ¿Autosave más reciente? → ofrecer restaurar
  5. Crear Historial, índice de referencias y servicios
  6. Arrancar la cola de tareas de fondo
  7a. Modo interfaz: ft.app(...) con app/estado y controladores
  7b. Modo render: servicio de render → salir
```

### 15.3 Cierre

1. Si hay cambios sin guardar: guardar, descartar o cancelar.
2. Detener la cola de tareas (las tareas en curso terminan o se cancelan).
3. Completar el diario pendiente.
4. Liberar decodificadores y cachés.

El `main.py` **crece por épicas**: en E0 solo interpreta argumentos; cada épica
conecta su parte.

### 15.4 Linux y PyCharm

**Entorno**

- Python 3.12 o superior en un entorno virtual (`.venv/`) creado desde PyCharm.
- Configuración de ejecución de PyCharm: script `main.py`, directorio de
  trabajo la raíz del repositorio; parámetros opcionales según 15.1 (por
  ejemplo, la ruta de un proyecto de prueba).

**Dependencias de sistema** (Debian/Ubuntu como referencia):

| Paquete | Para qué |
|---|---|
| `libmpv` (`libmpv2` o `libmpv1` según la versión de la distribución) | Control de video de Flet |
| `libgtk-3-0`, `libgstreamer1.0-0` | Ventana de escritorio de Flet |
| `vainfo` + controladores VAAPI (opcional) | Codificación por hardware Intel/AMD |
| Controlador NVIDIA con NVENC (opcional) | Codificación por hardware NVIDIA |
| `fonts-dejavu` o similares | Fuentes por defecto para los textos |

PyAV trae FFmpeg dentro de su paquete. En E0 se verifica que incluya los
codificadores necesarios (`libx264`, `prores_ks`); si falta alguno, se
documenta cómo usar el FFmpeg del sistema.

**Rutas**

- Todo con `pathlib`. Nada de rutas escritas a mano.
- Configuración de usuario (proyectos recientes, distribución) en
  `~/.config/editor/`; valores por defecto en `config/` del repositorio.

---

## 16. Interfaz de usuario

### 16.1 Secciones ajustables

Componente propio **`Divisor`** (barra arrastrable). Todas las secciones cambian
de tamaño y se pliegan; la distribución se guarda en `config/distribucion.json`.

```
┌──────────────┬────────────────────────────────────────┬──────────────┐
│ NAVEGADOR    │  MONITOR / LIENZO                      │ INSPECTOR    │
│ Proyecto     │ ┌── mesa de trabajo (gris) ──────────┐ │ x    200 px  │
│  └ cap0001   │ │ ┌──────── LIENZO 1280×720 ───────┐ │ │ y    150 px  │
│    ├ min00 ● │ │ │    ┌──────┐                    │ │ │ ancla 0,0    │
│    ├ min01 ◐ │ │ │    │ V2   │ ← asas             │ │ │ escala 1.00  │
│    └ …       │ │ │    └──────┘                    │ │ │ rotación 0°  │
│ Brutos       │ │ └────────────────────────────────┘ │ │ opacidad 100%│
│ Taller       │ └────────────────────────────────────┘ │ ◆ keyframes  │
│              │  cursor: (512, 288) px   zoom: 50 %    │              │
├──────────────┴────────────────────────────────────────┴──────────────┤
│ MAPA DEL CAPÍTULO: [00●][01◐][02○][03○] … [23○]                      │
├──────────────────────────────────────────────────────────────────────┤
│ TIMELINE · min02 · 02:00 ─────────────────────────────── 02:59       │
│ T1 │            ▐titulo▌                                             │
│ V2 │       ▐puerta-abre▌                                             │
│ V1 │▐ciudad-amanece████████▌▐calle██████████████████████▌            │
│ A1 │▐∿∿dialogo∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿▌                                     │
│ G  │▐∿∿∿∿ musica-tema (global) ∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿▌  │
└──────────────────────────────────────────────────────────────────────┘
```

| Sección | Contenido |
|---|---|
| Navegador | Proyecto → Capítulos → Minutos (estados de trabajo y render), Brutos, Taller |
| Monitor / Lienzo | Vista previa y control espacial |
| Inspector | Propiedades del Elemento, keyframes |
| Mapa del capítulo | 24 celdas con estado |
| Timeline | Capas del minuto, desbordes fantasma, pistas Global |
| Cola de render | Tareas y entregables |

### 16.2 Espacios de trabajo
**Taller**, **Minuto**, **Capítulo**, **Shorts**, **Render**: distribuciones
guardadas.

En **Shorts**: lista de Shorts del capítulo, monitor con el lienzo 16:9 y la
ventana 9:16 arrastrable, vista previa vertical al lado y timeline del rango
con los keyframes de la ventana.

### 16.3 Monitor como control espacial
- Mesa de trabajo gris: lo que queda fuera se ve semitransparente al editar.
- Reglas en píxeles y coordenada del cursor.
- Asas: mover, escalar, girar; ancla visible.
- Imán a bordes, centro, otros Elementos y guías.
- Márgenes seguros: acción 5 %, títulos 10 %.
- Guía 9:16 activable, para ver qué entra en un Short.
- Flechas = 1 px, Shift + flechas = 10 px.
- Al arrastrar, recuadro y asas se dibujan en el canvas de Flet al instante; la
  imagen se refresca ~10 veces por segundo y a calidad completa al soltar.

### 16.4 Zoom de la timeline

| Nivel | Muestra | Regla |
|---|---|---|
| Capítulo | 24 minutos | Minutos |
| Minuto | 60 segundos | Segundos |
| Segundos | ~10 segundos | Fotogramas |
| Fotograma | ~1 segundo | Cada fotograma |

### 16.5 Flujo del usuario
1. Crear proyecto y capítulo → `cap0001/min00`…`min23`.
2. Importar Brutos (se copian a `brutos/`) → revisar el fps detectado.
3. Preparar Piezas en el Taller: recortar en fotogramas nativos, elegir el
   método de conversión → hornear (24 fps, con asas) → banco.
4. Colocar Piezas en un minuto → copia materializada + gemelo.
5. Editar tiempo, posicionar y animar, efectos, transiciones, texto, audio.
6. Guardar → reconciliar, gemelos, guion.
7. Marcar el minuto como "listo".
8. Renderizar un minuto, un rango o el capítulo.
9. Opcional: crear Shorts sobre rangos del capítulo y renderizarlos.

---

## 17. Arquitectura del código

```
.
├── main.py                              punto de entrada único
├── requirements.txt
├── PROJECT.md
├── README.md
├── config/
│   ├── estandar.json                    valores para proyectos nuevos
│   ├── ajustes.json                     caché, autosave, historial, rutas recientes
│   ├── distribucion.json                espacios de trabajo
│   └── atajos.json                      atajos de teclado
└── editor/
    ├── __init__.py
    ├── core/
    │   ├── estandar.py                  N0
    │   ├── eventos.py                   N0 · BusEventos y tipos de evento
    │   ├── utiles/                      N0
    │   │   ├── interpolacion.py  matematicas.py  registro.py
    │   ├── tiempo/                      N1
    │   │   ├── granularidad.py          fotograma ↔ (min, seg, f)
    │   │   └── nomenclatura.py          nombres ↔ datos, IDs
    │   ├── espacio/                     N1
    │   │   ├── transform.py  lienzo.py  geometria.py
    │   ├── modelo/                      N2
    │   │   ├── composicion.py           base recursiva
    │   │   ├── proyecto.py  capitulo.py  minuto.py  global_.py
    │   │   ├── bruto.py  pieza.py  taller.py
    │   │   ├── elemento.py  capa.py  keyframe.py
    │   │   ├── efecto.py  transicion.py  texto.py
    │   │   ├── short.py                 Short + VentanaVertical
    │   │   └── referencias.py           índice Bruto → Pieza → Elemento → Minuto
    │   ├── comandos/                    N3
    │   │   ├── comando.py  compuesto.py  historial.py
    │   │   ├── agregar_elemento.py  quitar_elemento.py  mover_elemento.py
    │   │   ├── recortar_elemento.py  dividir_elemento.py  separar_audio.py
    │   │   ├── cambiar_propiedad.py  transformar_elemento.py
    │   │   ├── agregar_keyframe.py  quitar_keyframe.py
    │   │   ├── agregar_efecto.py  quitar_efecto.py  cambiar_transicion.py
    │   │   ├── ripple.py  roll.py  slip.py  slide.py
    │   │   ├── actualizar_fuente.py     tras hornear una Pieza
    │   │   ├── mover_minuto.py
    │   │   └── editar_short.py          crear, cambiar rango, mover ventana
    │   ├── proyecto_fs/                 N3
    │   │   ├── estructura.py  gemelo.py  manifiestos.py
    │   │   ├── diario.py  reconciliador.py  escaner.py
    │   │   ├── guion.py  autosave.py
    │   ├── motor/                       N3
    │   │   ├── motor_base.py
    │   │   ├── decodificador.py  codificador.py
    │   │   ├── cache_fotogramas.py
    │   │   ├── compositor.py  texto.py
    │   │   ├── conversion_fps.py        tiempo, conformar, cámara lenta, mezcla, interpolación
    │   │   ├── mezclador_audio.py
    │   │   └── efectos/                 biblioteca de efectos
    │   ├── servicios/                   N4
    │   │   ├── importacion.py           copiar a brutos + análisis (fps detectado, medido, vfr)
    │   │   ├── horneado.py              Pieza → conversión a 24 fps → archivo normalizado → comando
    │   │   ├── banco.py  miniaturas.py  forma_onda.py
    │   │   ├── huellas.py               huella y estado de render por minuto
    │   │   ├── vista_previa.py          niveles 1–4 y reloj de audio
    │   │   ├── render.py                minuto, rango, capítulo
    │   │   ├── ensamblado.py            unir minutos + audio
    │   │   ├── shorts.py                recomposición vertical 720×1280
    │   │   └── guardado.py              guardar y autosave
    │   ├── tareas/                      N4
    │   │   └── cola.py                  prioridades, instantáneas, cancelación
    │   └── plugins/                     N4
    │       └── gestor_plugins.py        efectos y exportadores externos
    └── app/                             N5–N6
        ├── estado.py                    puente eventos → Flet
        ├── controladores/
        │   ├── proyecto.py  medios.py  taller.py
        │   ├── timeline.py  reproduccion.py  render.py
        └── ui/
            ├── ventana.py               composición de secciones
            ├── divisor.py  distribucion.py
            ├── inicio.py                pantalla de inicio / proyectos recientes
            ├── navegador.py  monitor.py  asas.py  inspector.py
            ├── mapa_capitulo.py  timeline.py  taller.py
            ├── editor_curvas.py  cola_render.py  shorts.py
            ├── widgets/                 timecode, transporte, deslizador, rueda de color
            └── recursos/                iconos, temas
```

`requirements.txt`:

```
flet
flet-video          # control de video; verificar el nombre del paquete según la versión de Flet
av
numpy
opencv-python-headless
Pillow
```

Las versiones se fijan en E0. Las dependencias de sistema de Linux están en 15.4.

---

## 18. Unificación de qwen y deep

### 18.1 Qué aporta cada uno

| Fortaleza | Origen | Dónde queda |
|---|---|---|
| Estado central reactivo | qwen | `app/estado.py` + `core/eventos.py` |
| Controladores separados | qwen | `app/controladores/` |
| UI por carpetas: monitores, timeline, paneles, widgets | qwen | `app/ui/` |
| Paquete de tiempo dedicado | qwen | `core/tiempo/` |
| Comando base, compuesto e historial | qwen | `core/comandos/` |
| Comandos split, change_property, transform, add_keyframe | qwen | `dividir_elemento`, `cambiar_propiedad`, `transformar_elemento`, `agregar_keyframe` |
| Serialización del proyecto | qwen | `core/proyecto_fs/` |
| Servicios de medios, proxies, miniaturas, forma de onda | qwen | `core/servicios/` |
| Configuración rica y atajos | qwen | `config/` |
| Timebase exacto | deep | `core/tiempo/granularidad.py` |
| Ripple, roll, slide, slip | deep | `core/comandos/` |
| Interpolación de keyframes | deep | `core/utiles/interpolacion.py` |
| Editor de curvas | deep | `app/ui/editor_curvas.py` |
| Herramientas de timeline | deep | `app/ui/timeline.py` |
| Compositor espacial | deep | `core/motor/compositor.py` |
| Biblioteca de efectos | deep | `core/motor/efectos/` |
| Trabajos de render y render in-place | deep | `core/servicios/render.py`, `core/tareas/cola.py` |
| Gestor de plugins | deep | `core/plugins/` |
| Controles de audio | deep | `core/motor/mezclador_audio.py` + inspector |

### 18.2 Qué se descarta

| Elemento | Motivo |
|---|---|
| `mlt_engine` (ambos) | Instalación difícil; `motor_base` permite volver a agregarlo |
| pydantic | Se usa `dataclasses` + serialización explícita |
| `tests/` | Fuera del alcance de esta etapa |
| Directorio `project_workspace/` de qwen | Reemplazado por la estructura de proyecto de la sección 9 |
| Nombres en inglés | Se homologan al español (sección 3) |

### 18.3 Homologación

Todo módulo, clase, archivo y clave JSON sigue el glosario de la sección 3.
Ningún nombre de qwen o deep sobrevive tal cual: se traduce según las tablas
anteriores. Las carpetas `qwen_video_editor/` y `deep_video_editor/` se
eliminan en E0.

---

## 19. Épicas en orden sistemático

Cada épica depende de las anteriores. Hasta la E11 todo vive en `core/` y se
puede ejecutar con `main.py` en modo sin interfaz.

### Fase A — Fundamentos

**E0. Fundación**
- Eliminar `qwen_video_editor/` y `deep_video_editor/`.
- Crear el árbol de la sección 17 con módulos vacíos o mínimos.
- `main.py` con el análisis de argumentos (sección 15.1).
- `requirements.txt` con versiones fijadas y archivos de `config/`.
- Actualizar `README.md` para apuntar a este documento.

**E1. Base transversal (N0)**
- `estandar.py`, `eventos.py`, `utiles/` (registro, matemáticas, interpolación).

**E2. Tiempo y nomenclatura (N1)**
- `granularidad.py` y `nomenclatura.py`: conversión reversible, validación con
  la expresión regular, IDs únicos, nombres de Brutos, Piezas y Renders.

**E3. Espacio (N1)**
- `transform.py`, `lienzo.py`, `geometria.py`: matriz, compensación de ancla,
  descarte, región de interés, imán.

**E4. Modelo (N2)**
- Composición recursiva, Elemento, Capa, Keyframe, Minuto, Capítulo, Global,
  Proyecto, Bruto, Pieza, Taller, Efecto, Transición, Texto.
- Reglas: no solapamiento, marco temporal, desbordes.
- `referencias.py`.

### Fase B — Persistencia y edición

**E5. Disco (N3)**
- Estructura, gemelos, manifiestos, diario, reconciliador (mover y renombrar),
  escáner, guion, autosave.
- `main.py --nuevo` y `--escanear` operativos.

**E6. Comandos (N3)**
- Comando, compuesto, historial (100 pasos, fusión de arrastres).
- Edición básica, avanzada (ripple con alcance, roll, slip, slide), separar
  audio, actualizar fuente, mover minuto.

### Fase C — Motor y servicios

**E7. Decodificación y compositor (N3)**
- Decodificador, codificador, caché, compositor con alfa premultiplicado y
  modos de mezcla, texto.
- `conversion_fps.py`: los cinco métodos de conversión a 24 fps.
- Exportar un fotograma de prueba con capas apiladas y medir capas soportadas.

**E8. Mezclador de audio (N3)**
- Mezcla, volumen, paneo, fundidos, limitador.

**E9. Cola de tareas y servicios de medios (N4)**
- `tareas/cola.py` con prioridades e instantáneas.
- Importación con análisis de fps (detectado, medido, variable).
- Horneado normalizado a 24 fps con el método elegido y asas de 1 s; banco,
  miniaturas, forma de onda.

**E10. Render y ensamblado (N4)**
- Huellas y estados, render por minuto, ensamblado sin recodificar, audio en una
  pasada, versionado.
- `main.py --render` operativo.

**E11. Vista previa (N4)**
- Niveles 1–4, pre-render por minuto, reloj de audio.
- Servicio de guardado conectado a eventos.

### Fase D — Interfaz

**E12. Aplicación base (N5–N6)**
- `app/estado.py` (eventos → Flet), controladores.
- `ventana`, `divisor`, `distribucion`, espacios de trabajo, `inicio`, `navegador`.
- `main.py` abre la interfaz.

**E13. Monitor y control espacial**
- Monitor con los 4 niveles, transporte, mesa de trabajo, reglas, asas, ancla,
  imán, márgenes seguros, teclado.

**E14. Timeline y mapa del capítulo**
- Capas, zoom por granularidad, arrastre, herramientas, desbordes fantasma,
  pistas Global, mapa de 24 minutos con estados.

**E15. Taller**
- Brutos con fps detectado, medido y avisos de fps variable.
- Mini-timeline de la Pieza en **fotogramas nativos** de la fuente, selector de
  `fps_interpretado` y de método de conversión.
- Horneado, ida y vuelta con el minuto.

**E16. Inspector, keyframes y curvas**
- Inspector, keyframes en precisión de fotograma, editor de curvas bezier.

### Fase E — Capacidades creativas

**E17. Efectos, transiciones y texto**
- Color (brillo, contraste, saturación, temperatura, LUT), desenfoque, nitidez,
  croma; transiciones (fundido, deslizamiento, zoom, barrido); títulos y
  subtítulos; velocidad y rampas.

**E18. Audio avanzado**
- Keyframes de volumen, reducción automática de la música con voz, medidores.

**E19. Cola de render y exportación**
- Panel de cola de render, perfiles, H.265 / 10 bits, codificación por hardware.

**E20. Shorts verticales 9:16**
- Modelo `Short` y `VentanaVertical`, comando `editar_short`.
- Servicio de recomposición vertical a 720×1280 con huellas.
- Espacio de trabajo **Shorts** y guía 9:16 en el monitor.
- `main.py --shorts` operativo.

### Fase F — Cierre

**E21. Extras**
- Atajos configurables, plugins, subtítulos automáticos.

**E22. Documentación final**
- README completo y actualización de este documento con lo implementado.

### Dependencias entre épicas

```
E0 → E1 → E2 → E3 → E4 ─┬→ E5 ─┐
                        ├→ E6 ─┼→ E9 → E10 → E11 → E12 → E13 → E14 → E15 → E16
                        └→ E7 → E8 ─┘                                        │
                                                          E17 ← ─ ─ ─ ─ ─ ─ ─┘
                                                           └→ E18 → E19 → E20 → E21 → E22
```

E5, E6 y E7 dependen solo de E4 y pueden avanzar en paralelo; E9 necesita las
tres (y E8).

---

## 20. Especificaciones aspirables

Metas, no garantías.

| Aspecto | Objetivo |
|---|---|
| Banco al hornear | Más rápido que el tiempo real |
| Scrubbing | < 50 ms |
| Vista previa en vivo | 256×144 a 640×360 · 10–15 fps · 3–4 capas de video · audio sincronizado |
| Vista previa fluida | 960×540 · 24 fps |
| Fotograma exacto en pausa | ~150–300 ms |
| Timeline | 200–300 Elementos fluidos |
| Render final | 720p por defecto, hasta 4K · H.264 / H.265 · hardware si hay GPU |
| Deshacer | 100 pasos |
| Autosave | Cada 120 s |
| Plataforma | Linux (escritorio), ejecución desde PyCharm |
| Shorts | 720×1280 · 24 fps · recompuestos desde las fuentes, no ampliados |

---

## 21. Riesgos y decisiones abiertas

### 21.1 Riesgos

| Riesgo | Mitigación |
|---|---|
| Rendimiento del nivel 2 en Flet | Medir en E7/E11; bajar resolución o fps del banco; alternativa PySide6 sobre el mismo `core/` |
| Micro-cortes al cruzar minutos en el nivel 3 | Unir el rango sin recodificar antes de reproducir |
| Disco por materialización | Piezas cortas; aviso de espacio; posible modo de enlaces en el futuro |
| Cascadas de renombres (ripple de capítulo, mover minuto) | Alcance por minuto por defecto; aviso previo; diario |
| API de Flet cambiante | Versión fijada; Flet aislado en `app/ui` |
| Dependencias de sistema de Linux (libmpv, VAAPI) | Documentadas en 15.4; verificación en E0 |
| Fuentes con fps variable | Medición por marcas de tiempo, aviso en el Taller y método `tiempo` por defecto |
| Sin tests | Los modos `--escanear` y `--render` de `main.py` sirven como verificación manual; la arquitectura por niveles permite agregar tests más adelante sin reestructurar |

### 21.2 Decisiones

Todas cerradas en la revisión 3:

| # | Pregunta | Decisión |
|---|---|---|
| 1 | Duración del capítulo | **Exactamente 24 minutos**; capítulos del 1 al 1000 (`cap0001`–`cap1000`) |
| 2 | fps | **Solo 24 fps**; el nombre usa siempre `f00`–`f23` |
| 3 | Formatos de lienzo | **Solo 16:9**; el 9:16 existe como Short recortado (E20) |
| 4 | Plataforma y versión web | **Solo Linux de escritorio**; sin versión web |
| 5 | Asas | **1 segundo fijo** |
| 6 | fps de las fuentes al recortar | Interpretación por Bruto + método de conversión por Pieza (6.7) |
