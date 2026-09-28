# PROJECT.md — Editor de video por capítulos y minutos

Documento maestro de arquitectura. Recoge el enfoque, las decisiones y las
épicas acordadas. Es la referencia única: si el código contradice este
documento, se corrige uno de los dos de forma explícita.

- **Estado:** planificación. Todavía no hay código funcional.
- **Punto de partida:** los andamiajes vacíos `qwen_video_editor/` (base) y
  `deep_video_editor/` (capacidades avanzadas), que se fusionan en `editor/`.

---

## Índice

1. [Visión](#1-visión)
2. [Decisiones de base](#2-decisiones-de-base)
3. [Nomenclatura única (glosario)](#3-nomenclatura-única-glosario)
4. [Estándar objetivo HD720-24](#4-estándar-objetivo-hd720-24)
5. [Paradigma: composiciones anidadas sobre una rejilla de tiempo](#5-paradigma-composiciones-anidadas-sobre-una-rejilla-de-tiempo)
6. [Sistema de tiempo y granularidad](#6-sistema-de-tiempo-y-granularidad)
7. [Sistema espacial](#7-sistema-espacial)
8. [El Elemento: bloque fundamental](#8-el-elemento-bloque-fundamental)
9. [Estructura del proyecto en disco](#9-estructura-del-proyecto-en-disco)
10. [Sincronización disco–modelo](#10-sincronización-discomodelo)
11. [Motor de composición y transparencias](#11-motor-de-composición-y-transparencias)
12. [Vista previa híbrida en 4 niveles](#12-vista-previa-híbrida-en-4-niveles)
13. [Render por minuto y ensamblado del capítulo](#13-render-por-minuto-y-ensamblado-del-capítulo)
14. [Interfaz de usuario](#14-interfaz-de-usuario)
15. [Arquitectura del código](#15-arquitectura-del-código)
16. [Qué se aprovecha de qwen y deep](#16-qué-se-aprovecha-de-qwen-y-deep)
17. [Épicas en orden sistemático](#17-épicas-en-orden-sistemático)
18. [Especificaciones aspirables](#18-especificaciones-aspirables)
19. [Riesgos y preguntas abiertas](#19-riesgos-y-preguntas-abiertas)

---

## 1. Visión

Un editor de video de escritorio en Python que organiza **todo por tiempo y
por contexto**:

- Un **proyecto** contiene **capítulos**. Cada capítulo mide hasta **24
  minutos** y tiene una **carpeta por minuto**.
- Cada archivo (video, imagen, audio, texto) vive en la carpeta del minuto
  donde empieza, y **su nombre indica el instante exacto en que aparece**.
  Con el programa apagado, los nombres de los archivos ya cuentan la historia.
- Se edita en **secciones pequeñas**: un minuto a la vez para el trabajo fino
  de calidad, o el capítulo completo para el ritmo general.
- El render final puede ser **de 1 minuto, de un rango de minutos o de los 24
  minutos juntos**, y solo se re-renderizan los minutos que cambiaron.
- Antes de llegar a la timeline, el material se prepara en un **Taller**
  (sandbox), con su propia línea de tiempo, donde se hacen cortes,
  transformaciones y efectos.
- Composición espacial en **píxeles sobre un lienzo 1280×720**, con capas
  apiladas y transparencias.

Referencia de experiencia: un editor tipo **CapCut / Clipchamp**, con mejor
calidad de exportación, precisión de fotograma y una organización de archivos
legible por humanos.

---

## 2. Decisiones de base

| # | Decisión | Motivo |
|---|---|---|
| D1 | **Interfaz en Flet** con vista previa híbrida (sección 12) | Diseño moderno, multiplataforma y posible versión web. Sus límites de video se compensan con el banco de fotogramas y el pre-render |
| D2 | **`core/` en Python puro, sin ninguna librería de interfaz** | Testeable sin ventanas; permite una futura interfaz PySide6 sin tocar el núcleo |
| D3 | **Base de qwen + capacidades de deep** | qwen tiene la mejor organización (estado, controladores, serialización, tests); deep aporta la edición avanzada, el editor de curvas, la cola de render y los plugins |
| D4 | **Motor PyAV** (MLT queda fuera por ahora) | PyAV se instala fácil en todos los sistemas; `motor_base` deja la puerta abierta a otros motores |
| D5 | **Tiempo interno en fotogramas enteros** del capítulo | Precisión exacta, sin errores de redondeo |
| D6 | **Espacio en píxeles del lienzo 1280×720**, origen (0,0) arriba a la izquierda | Intuitivo; otras resoluciones solo multiplican por un factor |
| D7 | **El nombre del archivo cuenta la historia (tiempo); un archivo gemelo `.json` cuenta la puesta en escena (espacio)** | El nombre sigue corto y siempre verdadero; el detalle queda completo y animable |
| D8 | **Todo cambio del modelo pasa por un Comando** | Deshacer y rehacer funcionan siempre |
| D9 | **El disco se sincroniza al guardar**, no en cada arrastre | Evita renombres masivos y archivos bloqueados |
| D10 | **Español en todo el dominio**: carpetas, archivos, JSON, clases y pantalla | Un concepto, un nombre, en todas partes |
| D11 | **Las piezas del Taller se hornean** a un archivo | Reproducción rápida; lo pesado se calcula una sola vez |

Alternativa futura documentada: una interfaz profesional en **PySide6 (Qt)**
sobre el mismo `core/`, si se necesita reproducción multicapa a 720p en tiempo
real.

---

## 3. Nomenclatura única (glosario)

Regla: **cada concepto se llama igual en todas partes**. Sin tildes en el
código ni en los archivos; con tildes solo en la interfaz.

| Concepto | Carpeta | Archivo / prefijo | Clave JSON | Clase Python | En pantalla |
|---|---|---|---|---|---|
| Proyecto | `MiSerie/` | `proyecto.json` | `proyecto` | `Proyecto` | Proyecto |
| Capítulo | `cap01/` | `capitulo.json` | `capitulo` | `Capitulo` | Capítulo 01 |
| Minuto | `cap01/min00/` | `minuto.json`, prefijo `min00_` | `minuto` | `Minuto` | Minuto 00 |
| Global (pistas de todo el capítulo) | `cap01/global/` | mismo formato de nombre que un Elemento | `global` | `Global` | Global |
| Bruto (original importado) | `brutos/` | `bru0001_nombre__id.ext` | `bruto` | `Bruto` | Bruto |
| Taller (sandbox) | `taller/` | — | `taller` | `Taller` | Taller |
| Pieza (clip preparado en el Taller) | `taller/pie0001_nombre__id/` | `pieza.json`, `pieza.mp4` / `pieza.mov` | `pieza` | `Pieza` | Pieza |
| Elemento (algo colocado en el tiempo) | — | `min02_seg12f08_dur05s00_V2_nombre__id.ext` + gemelo `.json` | `elemento` | `Elemento` | Elemento |
| Capa | — | `V1`…`V9`, `A1`…`A9`, `T1`…`T9` | `capa` | `Capa` | V1, A1, T1 |
| Lienzo (cuadro 1280×720) | — | — | `lienzo` | `Lienzo` | Lienzo |
| Keyframe | — | — | `keyframes` | `Keyframe` | Keyframe |
| Render (entregable) | `cap01/render/` | `cap01_min00_v003.mp4` | `render` | `Render` | Render |
| Guion (reflejo legible) | `cap01/min00/` | `min00_guion.txt` | — | `Guion` | Guion |

### 3.1 Gramática del nombre de un Elemento

```
min02_seg12f08_dur05s00_V2_puerta-abre__a3f9.mov
 │     │    │    │        │   │            │    │
 │     │    │    │        │   │            │    └ extensión (.mov si tiene transparencia)
 │     │    │    │        │   │            └ ID estable (4 caracteres hex, único en el proyecto)
 │     │    │    │        │   └ nombre descriptivo en minúsculas-con-guiones
 │     │    │    │        └ capa: V video/imagen · A audio · T texto
 │     │    │    └ duración: segundos + fotogramas
 │     │    └ fotograma de inicio (f00–f23)
 │     └ segundo de inicio (seg00–seg59)
 └ minuto de inicio (min00–min23)
```

Reglas:

- **Ceros a la izquierda en todo**: el orden alfabético es el orden
  cronológico.
- Duración de un minuto o más: `dur01m05s00`.
- El **ID** nunca cambia, aunque el archivo se renombre o se mueva. Es lo que
  identifica al Elemento.
- Los minutos van del **00 al 23, como un reloj**: `min02_seg12` es
  exactamente `02:12` en el reproductor.
- **La carpeta y el prefijo son idénticos**: `cap01/min02/` solo contiene
  archivos que empiezan con `min02_`.
- Los nombres de los Renders: `cap01_min00_v003.mp4` (un minuto),
  `cap01_min05-08_v001.mp4` (rango), `cap01_completo_v002.mp4` (capítulo).

---

## 4. Estándar objetivo HD720-24

Un único estándar para toda la cadena, definido en un solo lugar
(`core/estandar.py` + `config/estandar.json`).

| Parámetro | Valor |
|---|---|
| Lienzo | **1280 × 720 px** |
| Origen | **(0, 0) = esquina superior izquierda** |
| Ejes | X hacia la derecha, **Y hacia abajo** |
| Fotogramas por segundo | **24 fps** (coincide con `f00`–`f23`) |
| Píxel | Cuadrado (1:1) |
| Color | sRGB / BT.709, 8 bits por canal |
| Composición interna | **RGBA con alfa premultiplicado** |
| Audio | 48 kHz, estéreo |
| Render final | H.264, CRF 18, yuv420p, AAC 192 kbps, `.mp4` |
| Piezas con transparencia | ProRes 4444, `.mov` |
| Piezas opacas | H.264 alta calidad, `.mp4` |
| Banco de vista previa | 20 % = **256 × 144 px**, 10 fps; JPEG (opaco) o WebP (con alfa) |
| Vista previa pre-renderizada | 960 × 540 (hasta 1280 × 720), 24 fps, H.264 `ultrafast` |

**Regla del marco:** lo que está dentro del lienzo se ve. Lo que está fuera
existe, se guarda y se puede animar, pero no aparece ni en la vista previa ni
en el render. Un elemento parcialmente dentro se recorta en el borde; uno
totalmente fuera no se procesa.

---

## 5. Paradigma: composiciones anidadas sobre una rejilla de tiempo

### 5.1 Todo es una Composición

Una **Pieza**, un **Minuto** y un **Capítulo** son el mismo tipo de objeto:
una línea de tiempo con Elementos. Un Elemento puede apuntar a un archivo **o
a otra composición** (el concepto de pre-composición de After Effects o de
clip compuesto de Final Cut y DaVinci, llevado a todo el sistema).

```
CAPÍTULO  (composición de hasta 24 min)
 ├── Global: música, narración, títulos generales
 └── MINUTO 00 … MINUTO 23  (composiciones de 60 s)
       └── Elementos que apuntan a PIEZAS  (composiciones cortas del Taller)
             └── Elementos que apuntan a BRUTOS  (archivos originales)
```

Consecuencia: **un solo motor**. El mismo editor, compositor, render e
historial de deshacer funcionan en todos los niveles; solo cambia la escala de
tiempo.

### 5.2 Los minutos son ventanas sobre un capítulo continuo

- El **capítulo es la línea de tiempo real y continua**.
- Cada **minuto es una ventana de 60 s** sobre ella, con su carpeta, sus
  archivos y su editor.
- Un Elemento **vive en la carpeta del minuto donde empieza**, pero puede
  **desbordarse** al siguiente. El minuto siguiente lo muestra como "entra
  desde min02" (referencia fantasma, sin copiar el archivo).
- Las transiciones que cruzan el límite de un minuto funcionan, porque el
  render de un minuto recorta la ventana del capítulo continuo.
- Lo que abarca todo el capítulo (música, narración) vive en `global/`.

### 5.3 Capas de trabajo (tiers)

```
DESARROLLO (abstracto)                    REPRODUCCIÓN (lo que se ve)
─────────────────────────                 ─────────────────────────────
T0  BRUTOS                                T2  MINUTO
    originales importados,                    60 s, composición de Piezas,
    nunca se modifican                        capas V1..V9 / A1..A9 / T1..T9
        │                                         │
        ▼                                         ▼
T1  TALLER (sandbox)                      T3  CAPÍTULO
    Piezas: recortes, color,                  24 minutos + Global
    velocidad, estabilizar,                       │
    transform, efectos.                           ▼
    Cada Pieza tiene su propia            T4  RENDER
    mini-timeline                             1 minuto, un rango
        │                                     o el capítulo completo
        └──── se coloca en ──────────►
```

Cada tier consume el resultado del anterior.

### 5.4 Por qué el Taller va separado de la timeline

| | Todo en la timeline | Taller separado |
|---|---|---|
| Timeline limpia | ❌ | ✅ Solo lo que va en el video |
| Reutilizar una pieza en varios minutos | ❌ Copiar | ✅ Una Pieza, muchas apariciones |
| Operaciones pesadas | ❌ Se recalculan en cada vista previa | ✅ Se hornean una vez |
| Experimentar sin miedo | ❌ | ✅ |

Ida y vuelta: doble clic en un Elemento del minuto abre su Pieza en el
Taller; al guardar la Pieza, el minuto se actualiza.

---

## 6. Sistema de tiempo y granularidad

### 6.1 Jerarquía

```
Proyecto
 └── Capítulo  ── hasta 24 minutos
      └── Minuto  ── 60 segundos
           └── Segundo  ── 24 fotogramas
                └── Fotograma  ← unidad mínima e indivisible
```

### 6.2 Reglas

- Internamente **todo es un número entero de fotogramas del capítulo**.
- Minuto, segundo, fotograma y el nombre del archivo son **vistas calculadas**
  de ese número:

  ```
  fotograma 3176 del capítulo (24 fps)
    = minuto 02, segundo 12, fotograma 08
    = "min02_seg12f08"
  ```

- La tasa de fotogramas es una fracción exacta (`Fraction(24, 1)`), nunca un
  decimal.
- La conversión es **reversible**: nombre → fotograma → nombre devuelve
  exactamente el mismo texto.
- Los keyframes se guardan **relativos al inicio del Elemento**, en
  fotogramas. Mover el Elemento no obliga a reescribirlos.

### 6.3 Dimensiones de tiempo de un Elemento

| Propiedad | Significado |
|---|---|
| `inicio` | Fotograma del capítulo donde empieza (sale del nombre) |
| `duracion` | Fotogramas que dura (sale del nombre) |
| `fuente_entrada` | Desde qué fotograma del archivo se empieza a usar |
| `velocidad` | 1.0 normal, 2.0 rápido, 0.5 lento, negativo = reversa |

### 6.4 Ediciones de tiempo (de deep)

| Edición | Qué cambia | Qué queda fijo |
|---|---|---|
| Trim | Entrada o salida del Elemento | Todo lo demás; queda un hueco |
| Ripple | Entrada o salida | Los Elementos siguientes se corren para no dejar hueco |
| Roll | El corte entre dos Elementos | La duración total |
| Slip | El contenido (`fuente_entrada`) | La posición en la timeline |
| Slide | La posición del Elemento | Su contenido; los vecinos se ajustan |

Ripple, Roll y Slide tocan varios Elementos a la vez; se implementan como
**comandos compuestos** para deshacerse en un solo paso.

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
  │   │        │ 400 × 300  │   de sí mismo      │
  │   │        └────────────┘                    │
  │   └──────────────────────────────────────────┘ ┌────┐
(0,720)                                   (1280,720)│    │ ← fuera: existe,
                                                    └────┘   no se ve
```

### 7.2 Propiedades espaciales de un Elemento

| Propiedad | Unidad | Por defecto | Significado |
|---|---|---|---|
| `x`, `y` | px del lienzo | `0, 0` | Dónde cae el ancla del Elemento en el lienzo |
| `ancla_x`, `ancla_y` | px del propio Elemento | `0, 0` | Punto que se coloca en (x, y); centro de giro y escala |
| `ancho`, `alto` | px | tamaño original | Tamaño natural del archivo (solo lectura) |
| `escala_x`, `escala_y` | factor | `1.0` | 0.5 = mitad, 2.0 = doble; negativo = espejo |
| `rotacion` | grados | `0` | Sentido horario |
| `recorte` | px (izq, arr, der, abj) | `0,0,0,0` | Recorta el Elemento antes de colocarlo |
| `opacidad` | 0.0 – 1.0 | `1.0` | Transparencia global |
| `mezcla` | modo | `normal` | normal, multiplicar, pantalla, superponer, sumar |
| `ajuste_inicial` | modo | `original` | Al colocarlo: original, encajar, llenar, estirar |

- Con el ancla por defecto, **`x, y` es la esquina superior izquierda**.
- Al mover el ancla, el editor compensa `x, y` para que el Elemento no salte.
- Se permiten coordenadas negativas y mayores que el lienzo (animaciones de
  entrada y salida).
- **Todas las propiedades son animables con keyframes**.

### 7.3 Cálculo

Todas las propiedades se combinan en una matriz afín 2×3:

```
M = Trasladar(x, y) · Rotar(rotacion) · Escalar(escala_x, escala_y) · Trasladar(-ancla_x, -ancla_y)
```

Proceso por Elemento y por fotograma:

1. Rectángulo que ocupa en el lienzo (sus 4 esquinas transformadas).
2. **Descarte**: si no toca el lienzo, se salta sin decodificar.
3. **Región de interés**: intersección con el lienzo.
4. `cv2.warpAffine` solo sobre esa región.
5. Mezcla sobre el lienzo con opacidad y modo de mezcla.

Para cualquier otra resolución (vista previa al 20 %, exportación distinta) se
multiplica la matriz por un factor de escala. Lo que se ve es lo que se
exporta.

---

## 8. El Elemento: bloque fundamental

El Elemento es **una ventana de tiempo sobre un archivo, colocada en el
lienzo y en la timeline, cuyas propiedades son parámetros animables**.

### 8.1 Dimensiones

| Dimensión | Contenido |
|---|---|
| Identidad | `id`, nombre, capa, estado (activo, bloqueado, silenciado), vínculos |
| Fuente | Referencia a un Bruto o a una Pieza; nunca contiene el video |
| Tiempo | `inicio`, `duracion`, `fuente_entrada`, `velocidad` |
| Espacio | Sección 7.2 |
| Apariencia | Pila ordenada de efectos |
| Audio | `volumen`, `paneo`, fundidos |
| Animación | Keyframes sobre cualquier parámetro |
| Relaciones | Capa, transiciones con vecinos, desborde a otro minuto |

### 8.2 Capacidad central: evaluarse

```
elemento.evaluar(fotograma N)
  1. ¿Estoy activo en N?                 → si no, no aporto nada
  2. ¿Toco el lienzo?                    → si no, no aporto nada
  3. N → fotograma de la fuente          → tiempo (fuente_entrada, velocidad)
  4. Pido ese fotograma al motor         → PyAV + caché
  5. Evalúo mis parámetros en N          → keyframes interpolados
  6. Aplico efectos en orden
  7. Devuelvo imagen RGBA + matriz       → al compositor
```

El monitor, las miniaturas, la vista previa y el render usan exactamente este
mismo proceso; solo cambia el destino y la resolución.

### 8.3 Archivo gemelo

Cada Elemento son **dos archivos con el mismo nombre base**:

```
min02_seg12f08_dur05s00_V2_puerta-abre__a3f9.mov    ← contenido (qué se ve)
min02_seg12f08_dur05s00_V2_puerta-abre__a3f9.json   ← gemelo (cómo y dónde)
```

```json
{
  "id": "a3f9",
  "fuente": { "tipo": "pieza", "ref": "pie0001_puerta-abre__a3f9" },
  "tiempo": {
    "inicio": "min02_seg12f08",
    "duracion": "dur05s00",
    "fuente_entrada": 0,
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
  "audio": { "volumen": 1.0, "paneo": 0.0 }
}
```

### 8.4 Reparto de la información

| Dónde | Qué guarda |
|---|---|
| Carpeta (`cap01/min02/`) | Capítulo y minuto: contexto grueso |
| Nombre | Inicio, duración, capa, nombre, ID: **la historia** |
| Gemelo `.json` | Espacio, keyframes, efectos, detalle de tiempo: **la puesta en escena** |
| `minuto.json` | Solo datos del minuto: notas, estado, huella de render |
| `min02_guion.txt` | Reflejo legible generado al guardar; nunca se edita ni se lee |

La posición espacial **no va en el nombre**: tiene muchas dimensiones, suele
estar animada y cambia constantemente. En el nombre sería incompleta y
obligaría a renombrar en cada ajuste.

Ejemplo de guion generado:

```
MINUTO 02 · cap01 · lienzo 1280×720 · 24 fps
───────────────────────────────────────────────────────────────────
02:00.00  V1  ciudad-amanece   12s08  pos (0,0)       esc 1.00  pantalla completa
02:12.08  V2  puerta-abre       5s00  pos (-400,150)→(200,150)  entra desde izquierda
02:14.00  V3  logo              3s00  pos (1080,20)   esc 0.50  esquina sup. derecha
02:17.08  A1  dialogo-juan     40s00  —               vol 100 %
```

---

## 9. Estructura del proyecto en disco

```
MiSerie/                                    ← PROYECTO
├── proyecto.json                           estándar, lista de capítulos
├── brutos/                                 T0 · originales, nunca se modifican
│   ├── video/   bru0001_toma-calle__7c21.mp4
│   ├── audio/   bru0002_entrevista__91be.wav
│   └── imagen/  bru0003_logo__0f3a.png
├── taller/                                 T1 · sandbox
│   └── pie0001_puerta-abre__a3f9/
│       ├── pieza.json                      receta: fuente, recortes, efectos, transform
│       └── pieza.mov                       resultado horneado (.mp4 si es opaca)
├── cap01/                                  ← CAPÍTULO
│   ├── capitulo.json
│   ├── global/
│   │   ├── min00_seg00f00_dur24m00s00_A1_musica-tema__c810.wav
│   │   └── min00_seg00f00_dur24m00s00_A1_musica-tema__c810.json
│   ├── min00/                              ← MINUTO 00:00–00:59
│   │   ├── minuto.json
│   │   ├── min00_guion.txt
│   │   ├── min00_seg00f00_dur12s08_V1_ciudad-amanece__4b7e.mp4
│   │   ├── min00_seg00f00_dur12s08_V1_ciudad-amanece__4b7e.json
│   │   ├── min00_seg12f08_dur05s00_V2_puerta-abre__a3f9.mov
│   │   └── min00_seg12f08_dur05s00_V2_puerta-abre__a3f9.json
│   ├── min01/ … min23/
│   └── render/
│       ├── cap01_min00_v003.mp4
│       ├── cap01_min05-08_v001.mp4
│       └── cap01_completo_v002.mp4
├── cap02/ …
├── .diario/                                operaciones de disco pendientes
└── .cache/                                 BORRABLE: bancos, vistas previas, formas de onda
```

Con el programa cerrado, abrir `cap01/min00/` ya cuenta el minuto en orden.

---

## 10. Sincronización disco–modelo

**Principio:** el modelo en memoria es la verdad mientras se edita. Al
guardar, el disco se convierte en su reflejo legible. Con el programa
apagado, el disco cuenta la historia completa.

| Problema | Solución |
|---|---|
| Renombrar en cada arrastre | El modelo cambia al instante; **los archivos se renombran al guardar** |
| Archivo en uso (Windows) | El reconciliador libera el archivo, renombra y reintenta |
| Corte a mitad de operación | **Diario** en `.diario/`: primero se escribe el plan y luego se ejecuta; al reabrir se completa o se revierte |
| Deshacer | Solo cambia el modelo; el reconciliador vuelve a sincronizar los nombres |
| El nombre no cabe todo | El gemelo `.json` guarda el detalle |
| Se pierde un gemelo | El **escáner** rescata tiempo y capa desde el nombre y coloca el Elemento en (0,0), escala 1: se pierde la puesta en escena, nunca la historia |
| Duplicar archivos pesados | Los Brutos quedan en `brutos/`; en los minutos van Piezas horneadas cortas |
| Renombres manuales | El ID estable permite reconocer el archivo |

Componentes:

- **`estructura`**: crea el proyecto, los capítulos y las carpetas `min00`–`min23`.
- **`reconciliador`**: compara modelo y disco, calcula el plan de renombres,
  lo escribe en el diario y lo ejecuta. El contenido y su gemelo se renombran
  siempre juntos.
- **`escaner`**: reconstruye el modelo leyendo carpetas, nombres y gemelos.

---

## 11. Motor de composición y transparencias

### 11.1 Apilado

```
V1 (fondo)   ciudad.mp4           → lienzo
V2           personaje.mov (alfa) → encima de V1
V3           logo.png (alfa)      → encima de V2
T1           título (texto)       → encima de todo
```

Mezcla "sobre" con alfa premultiplicado, que evita halos oscuros en los bordes:

```
resultado = frente + fondo × (1 − alfa_frente)
```

Las capas se procesan de abajo hacia arriba: V1…V9 y después T1…T9.

### 11.2 Formatos con transparencia

| Formato | ¿Alfa? | Nota |
|---|---|---|
| PNG, WebP, GIF | ✅ | Imágenes |
| ProRes 4444 `.mov` | ✅ | **Formato de las Piezas con alfa** |
| QuickTime Animation / PNG en `.mov` | ✅ | Sin pérdida, pesado |
| VP9 `.webm` | ⚠️ | Solo con el decodificador libvpx |
| Secuencia de PNG | ✅ | |
| MP4 H.264 / H.265 | ❌ | Siempre opaco |

Sin alfa de origen, la transparencia se crea en el Taller (croma, máscaras,
recortes) y se hornea con alfa.

### 11.3 Librerías

| Librería | Uso |
|---|---|
| PyAV | Decodificar video y audio (alfa incluido); codificar el render |
| Pillow | Imágenes, PNG con alfa, texto con fuentes TTF |
| OpenCV | `warpAffine`, escalado, color, croma |
| numpy | Mezcla, opacidad, modos de mezcla |
| numba (opcional) | Acelerar bucles de píxeles |
| moderngl (futuro) | Composición por GPU si hace falta más potencia |

Interpolación: `INTER_AREA` para reducir, `INTER_LINEAR` al arrastrar en vivo,
`INTER_CUBIC` / `INTER_LANCZOS4` para ampliar y para el render final.

### 11.4 Optimizaciones

- **Descarte** de Elementos fuera del lienzo: costo cero.
- **Región de interés**: solo se transforma la zona visible.
- **Caché** de imágenes fijas ya transformadas mientras sus parámetros no cambien.
- **Caché de fotogramas** decodificados (LRU, 512 MB por defecto).
- Decodificar al tamaño necesario, no siempre a resolución completa.

### 11.5 Escalabilidad estimada (a validar en la épica E6)

| Escenario | Límite práctico estimado |
|---|---|
| Imágenes fijas | Decenas de capas |
| Video 720p por capa | ~5–8 capas simultáneas en vista previa a 720p |
| Vista previa al 20 % | ~10–15 capas a 10 fps |
| Render final | Sin límite; solo tarda más |

---

## 12. Vista previa híbrida en 4 niveles

Flet no está pensado para enviar 24 imágenes grandes por segundo desde Python.
La solución combina cuatro niveles:

```
                       ┌──────────────────────────────────────┐
  AL IMPORTAR ────────►│ NIVEL 0: BANCO DE FOTOGRAMAS          │
  (segundo plano)      │ 256×144 · 10 fps · JPEG / WebP alfa  │
                       │ + tira de miniaturas + forma de onda │
                       └──────────────┬───────────────────────┘
          ┌─────────────────┬─────────┴────────┬───────────────────┐
          ▼                 ▼                  ▼                   ▼
   SCRUBBING         EDITANDO + PLAY     PLAY FLUIDO          EN PAUSA
   Nivel 1           Nivel 2             Nivel 3              Nivel 4
   imagen del banco  composición en      video pre-renderizado fotograma exacto
   < 50 ms           vivo desde el banco control Video         desde el original
                     10–15 fps + audio   960×540 · 24 fps     ~150–300 ms
```

### 12.1 Nivel 0 — Banco de fotogramas

```
.cache/banco/<id>/
├── f000000.jpg …      256×144, 10 fps (WebP si el Elemento tiene alfa)
├── indice.json        fotograma del banco ↔ fotograma del original
├── tira.jpg           miniaturas para dibujar el clip en la timeline
└── onda.json          picos de audio
```

Aproximadamente 6 MB por minuto de video. Se genera en segundo plano al
importar, más rápido que el tiempo real.

### 12.2 Nivel 1 — Scrubbing
Imagen del banco más cercana, sin composición.

### 12.3 Nivel 2 — Composición en vivo
En cada tic (10–15 por segundo): Elementos activos → imágenes del banco →
transform → mezcla → JPEG → `ft.Image`. Muestra la edición real sin esperar
render.

### 12.4 Nivel 3 — Pre-render por minuto
- Cada minuto tiene una **huella** (hash de todo lo que contiene).
- Al dejar de editar, se renderiza en segundo plano cada minuto cuya huella
  cambió: 960×540, 24 fps, H.264 `ultrafast`.
- El control Video de Flet lo reproduce con aceleración por hardware.
- En el mapa del capítulo: **verde** = listo, **rojo** = pendiente. En zona
  roja se usa el nivel 2.

### 12.5 Nivel 4 — Fotograma exacto en pausa
Decodifica del original y compone a la resolución real del monitor; JPEG
calidad 90.

### 12.6 Audio como reloj maestro
- Mezcla de audio de vista previa generada en segundo plano.
- El nivel 2 pregunta en cada tic en qué instante va el audio y muestra la
  imagen de ese momento; si se retrasa, **salta fotogramas** en vez de
  desincronizarse.

---

## 13. Render por minuto y ensamblado del capítulo

```
Capítulo:  [00✅][01✅][02🔴][03✅] … [23✅]
                        │
            solo se re-renderiza el minuto 02
                        │
                        ▼
   Capítulo completo = unir minutos SIN recodificar
```

- **Render de un minuto**: recorta la ventana del capítulo continuo
  (incluye desbordes y Global), a resolución y calidad finales, desde los
  **originales**.
- Se fuerza un **fotograma clave al inicio de cada minuto** para poder unir
  sin recodificar.
- **El audio del capítulo se renderiza en una sola pasada** y se une al video
  concatenado, para evitar clics en los límites.
- Entregables: un minuto, un rango de minutos o el capítulo completo.
- Versionado en el nombre: `_v001`, `_v002`…

Calidad por encima de CapCut / Clipchamp:

1. Exportación siempre desde los originales, nunca desde proxies.
2. Escalado Lanczos.
3. CRF 16–18.
4. Opción H.265 y 10 bits.
5. Codificación por hardware (NVENC, QuickSync, VideoToolbox) cuando exista.
6. Sin marca de agua, sin nube.

---

## 14. Interfaz de usuario

### 14.1 Secciones ajustables

Componente propio **`Divisor`** (barra arrastrable que redimensiona los paneles
vecinos). Todas las secciones cambian de tamaño, se pueden plegar y la
distribución se guarda en `config/distribucion.json`.

```
┌──────────────┬────────────────────────────────────────┬──────────────┐
│ NAVEGADOR    │  MONITOR / LIENZO                      │ INSPECTOR    │
│ Proyecto     │ ┌── mesa de trabajo (gris) ──────────┐ │ x    200 px  │
│  └ cap01     │ │ ┌──────── LIENZO 1280×720 ───────┐ │ │ y    150 px  │
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
| Navegador | Árbol Proyecto → Capítulos → Minutos (con estado), Brutos, Taller |
| Monitor / Lienzo | Vista previa y control espacial |
| Inspector | Propiedades del Elemento, keyframes |
| Mapa del capítulo | 24 celdas de minuto con color de estado |
| Timeline | Capas del minuto, alto de capa ajustable, zoom por niveles |
| Cola de render | Minutos pendientes y entregables |

### 14.2 Espacios de trabajo
Distribuciones guardadas: **Taller**, **Minuto**, **Capítulo**, **Render**.

### 14.3 Monitor como control espacial
- **Mesa de trabajo** gris alrededor del lienzo: lo que queda fuera se ve
  semitransparente al editar y no aparece en el render.
- **Reglas en píxeles** y coordenada del cursor en vivo.
- **Asas**: mover, escalar (esquinas), girar; punto de ancla visible.
- **Imán** a bordes y centro del lienzo, a otros Elementos y a guías.
- **Márgenes seguros**: acción 5 %, títulos 10 %.
- Teclado: flechas = 1 px, Shift + flechas = 10 px.
- Al arrastrar, el recuadro y las asas se dibujan en el canvas de Flet al
  instante; la imagen compuesta se refresca ~10 veces por segundo y a calidad
  completa al soltar.

### 14.4 Zoom de la timeline por granularidad

| Nivel | Muestra | Regla |
|---|---|---|
| Capítulo | 24 minutos | Minutos |
| Minuto | 60 segundos | Segundos |
| Segundos | ~10 segundos | Fotogramas |
| Fotograma | ~1 segundo | Cada fotograma |

### 14.5 Flujo del usuario
1. Crear proyecto y capítulo → se generan `cap01/min00`…`min23`.
2. Importar Brutos → banco, miniaturas y forma de onda en segundo plano.
3. Preparar Piezas en el Taller → hornear.
4. Colocar Piezas en un minuto → nace el Elemento.
5. Editar tiempo (trim, ripple, roll, slip, slide).
6. Posicionar y animar en el lienzo.
7. Efectos, transiciones, texto, audio.
8. Guardar → renombres, gemelos y guion.
9. Renderizar un minuto, un rango o el capítulo.

---

## 15. Arquitectura del código

### 15.1 Capas

```
┌──────────────────────────────────────────────────────────┐
│ 4. INTERFAZ (app/ui) – Flet                              │
│    Solo muestra y captura acciones                       │
├──────────────────────────────────────────────────────────┤
│ 3. APLICACIÓN (app/controladores + app/estado)           │
│    Traduce acciones en comandos; emite cambios           │
├──────────────────────────────────────────────────────────┤
│ 2. OPERACIONES (core/comandos + core/proyecto_fs)        │
│    Comandos con deshacer; sincronización con el disco    │
├──────────────────────────────────────────────────────────┤
│ 1. NÚCLEO (core/tiempo, espacio, modelo, motor)          │
│    Proyecto → Capítulo → Minuto → Elemento → Keyframe    │
└──────────────────────────────────────────────────────────┘
   Cada capa conoce solo a la de abajo. core/ no importa Flet.
```

Reglas de oro:

1. Nada modifica el modelo excepto un Comando.
2. El núcleo no sabe que existe una interfaz.
3. La interfaz no calcula nada; solo muestra y reacciona a cambios.

### 15.2 Árbol

```
editor/
├── core/
│   ├── estandar.py                 HD720-24 en un solo lugar
│   ├── tiempo/
│   │   ├── granularidad.py         fotograma ↔ (min, seg, f)
│   │   └── nomenclatura.py         nombre de archivo ↔ datos del Elemento
│   ├── espacio/
│   │   ├── lienzo.py               límites, recorte, descarte
│   │   ├── transform.py            propiedades → matriz afín
│   │   └── geometria.py            rectángulos, intersección, imán
│   ├── modelo/
│   │   ├── composicion.py          base recursiva
│   │   ├── proyecto.py  capitulo.py  minuto.py  global_.py
│   │   ├── bruto.py  pieza.py  taller.py
│   │   ├── elemento.py             bloque fundamental
│   │   ├── capa.py
│   │   ├── keyframe.py             interpolación
│   │   └── efecto.py  transicion.py
│   ├── proyecto_fs/
│   │   ├── estructura.py           crear carpetas
│   │   ├── gemelo.py               leer/escribir el .json del Elemento
│   │   ├── guion.py                generar minNN_guion.txt
│   │   ├── diario.py               operaciones atómicas
│   │   ├── reconciliador.py        renombrar al guardar
│   │   └── escaner.py              reconstruir desde el disco
│   ├── comandos/
│   │   ├── comando.py  compuesto.py  historial.py
│   │   ├── agregar_elemento.py  mover_elemento.py  recortar_elemento.py
│   │   ├── dividir_elemento.py  cambiar_propiedad.py  transformar_elemento.py
│   │   ├── agregar_keyframe.py  agregar_efecto.py  quitar_efecto.py
│   │   ├── ripple.py  roll.py  slip.py  slide.py
│   │   └── hornear_pieza.py  mover_minuto.py
│   ├── motor/
│   │   ├── motor_base.py
│   │   ├── decodificador.py        PyAV, alfa incluido
│   │   ├── cache_fotogramas.py     LRU
│   │   ├── banco.py                nivel 0
│   │   ├── compositor.py           descarte → región → warpAffine → mezcla
│   │   ├── texto.py                Pillow + fuentes
│   │   ├── efectos/                biblioteca de efectos
│   │   ├── render_minuto.py
│   │   ├── ensamblador.py          unir minutos + audio en una pasada
│   │   └── trabajo_render.py       cola de trabajos
│   ├── servicios/
│   │   ├── analizador_medios.py  miniaturas.py  forma_onda.py
│   │   └── exportacion.py
│   ├── plugins/
│   │   └── gestor_plugins.py
│   └── utiles/
│       ├── interpolacion.py  matematicas.py  registro.py
├── app/
│   ├── main.py
│   ├── estado.py
│   ├── controladores/
│   │   ├── proyecto.py  medios.py  timeline.py  reproduccion.py  render.py
│   ├── ui/
│   │   ├── divisor.py  distribucion.py
│   │   ├── navegador.py  monitor.py  asas.py  inspector.py
│   │   ├── mapa_capitulo.py  timeline.py  taller.py
│   │   ├── editor_curvas.py  cola_render.py
│   │   └── widgets/  (timecode, transporte, deslizador, rueda de color)
│   └── recursos/  (iconos, temas)
├── config/
│   ├── estandar.json  distribucion.json  atajos.json  ajustes.json
└── tests/
```

---

## 16. Qué se aprovecha de qwen y deep

| Origen | Módulo original | Destino en `editor/` |
|---|---|---|
| qwen | `app/state/app_state.py` | `app/estado.py` |
| qwen | `app/controllers/*` | `app/controladores/*` |
| qwen | `app/ui/monitors`, `timeline`, `panels`, `widgets` | `app/ui/*` (adaptados a Flet híbrido) |
| qwen | `core/time/*` | `core/tiempo/*` |
| qwen | `core/model/*` | `core/modelo/*` |
| qwen | `core/commands/base_command`, `compound_command`, `history` | `core/comandos/comando`, `compuesto`, `historial` |
| qwen | `core/serialization/*` | `core/proyecto_fs/gemelo` + manifiestos |
| qwen | `core/services/*` | `core/servicios/*`, `core/motor/banco` |
| qwen | `config/settings.json` | `config/ajustes.json` |
| deep | `core/model/timebase.py` | `core/tiempo/granularidad.py` |
| deep | `core/commands/ripple_delete`, `roll_edit`, `slide_edit`, `slip_edit` | `core/comandos/ripple`, `roll`, `slide`, `slip` |
| deep | `core/utils/interpolation.py` | `core/utiles/interpolacion.py` |
| deep | `app/ui/graph_editor.py` | `app/ui/editor_curvas.py` |
| deep | `app/ui/timeline_tools.py` | herramientas de `app/ui/timeline.py` |
| deep | `core/engines/spatial_compositor.py` | `core/motor/compositor.py` |
| deep | `core/engines/effects_library.py` | `core/motor/efectos/` |
| deep | `core/engines/render_job.py`, `render_in_place.py` | `core/motor/trabajo_render.py` |
| deep | `core/plugins/plugin_manager.py` | `core/plugins/gestor_plugins.py` |
| — | MLT (`mlt_engine`) | Fuera por ahora; `motor_base` permite agregarlo |

`qwen_video_editor/` y `deep_video_editor/` se conservan como referencia hasta
la épica E19 y luego se eliminan.

---

## 17. Épicas en orden sistemático

Cada épica depende de las anteriores. Hasta la E9 todo está en `core/` y se
puede trabajar sin interfaz.

### Fase A — Fundamentos

**E0. Fundación del repositorio**
- Crear `editor/` con el árbol de la sección 15.2 (módulos vacíos).
- `requirements.txt`: `flet`, `flet-video`, `av`, `numpy`, `opencv-python-headless`, `Pillow`, `pydantic`.
- `core/estandar.py` y `config/estandar.json` con HD720-24.
- Actualizar `README.md` para apuntar a este documento.
- *Resultado:* estructura lista y estándar definido en un solo lugar.

**E1. Tiempo y nomenclatura**
- `granularidad.py`: fotograma ↔ (min, seg, f), duraciones, `Fraction`.
- `nomenclatura.py`: nombre ↔ datos (inicio, duración, capa, nombre, ID, extensión); validación; generación de IDs únicos; nombres de Brutos, Piezas y Renders.
- *Resultado:* conversión reversible y exacta entre fotogramas y nombres.

**E2. Espacio**
- `transform.py`: propiedades → matriz afín; compensación al mover el ancla.
- `lienzo.py`: rectángulo transformado, descarte, región de interés.
- `geometria.py`: intersecciones e imán.
- *Resultado:* posición en píxeles exacta y cálculo de visibilidad.

**E3. Modelo**
- `composicion`, `elemento`, `capa`, `keyframe`, `minuto`, `capitulo`, `global_`, `proyecto`, `bruto`, `pieza`, `taller`, `efecto`, `transicion`.
- Desborde de Elementos entre minutos (referencia fantasma).
- Evaluación de parámetros con keyframes relativos al inicio.
- *Resultado:* el proyecto completo representado en memoria.

### Fase B — Persistencia y edición

**E4. Sistema de archivos del proyecto**
- `estructura`: crear proyecto, capítulo y `min00`–`min23`.
- `gemelo`: leer y escribir el `.json` de cada Elemento.
- `diario` + `reconciliador`: renombres atómicos al guardar.
- `escaner`: reconstruir el modelo desde el disco, incluso sin gemelos.
- `guion`: generar `minNN_guion.txt`.
- *Resultado:* un proyecto real en disco que se guarda, se reabre y se rescata.

**E5. Comandos e historial**
- `comando`, `compuesto`, `historial` (límite de 100 pasos, fusión de arrastres).
- Edición básica: agregar, mover, recortar, dividir, cambiar propiedad, transformar, keyframes, efectos.
- Edición avanzada: ripple, roll, slip, slide.
- Comandos de nivel: mover un minuto, hornear una Pieza.
- *Resultado:* toda la edición con deshacer, sin interfaz.

### Fase C — Motor

**E6. Decodificación y compositor** ← **hito de validación**
- `decodificador` (PyAV, alfa), `cache_fotogramas`.
- `compositor`: descarte → región → `warpAffine` → mezcla premultiplicada; modos de mezcla.
- `texto` con Pillow.
- Exportar un fotograma de prueba con videos y PNG apilados con alfa.
- *Resultado:* medir cuántas capas soporta el equipo real y ajustar las estimaciones de la sección 11.5.

**E7. Banco de fotogramas y servicios de medios**
- `analizador_medios`, `banco` (JPEG / WebP con alfa), `miniaturas`, `forma_onda`.
- Generación en segundo plano al importar.
- *Resultado:* nivel 0 de la vista previa listo.

**E8. Render por minuto y ensamblado**
- `render_minuto` con fotograma clave inicial, desde los originales.
- `ensamblador`: unir minutos sin recodificar + audio del capítulo en una pasada.
- Huella por minuto y render incremental; versionado de entregables.
- *Resultado:* exportar 1 minuto, un rango o el capítulo completo.

**E9. Vista previa híbrida**
- Niveles 1 a 4, pre-render por minuto en segundo plano, audio como reloj maestro.
- *Resultado:* todo el sistema de vista previa operativo desde `core/`.

### Fase D — Interfaz (Flet)

**E10. Interfaz base**
- `main`, `estado`, controladores.
- `divisor` y `distribucion`; espacios de trabajo Taller, Minuto, Capítulo, Render.
- `navegador` del proyecto.
- *Resultado:* abrir un proyecto y navegar capítulos y minutos.

**E11. Monitor y control espacial**
- Monitor con los 4 niveles de vista previa y controles de transporte.
- Mesa de trabajo, reglas, coordenada del cursor, asas, ancla, imán, márgenes seguros, teclado.
- *Resultado:* ver y posicionar Elementos en el lienzo.

**E12. Timeline y mapa del capítulo**
- Capas con alto ajustable, zoom por granularidad, arrastrar, imán, herramientas (selección, cuchilla, ripple, roll, slip, slide).
- Mapa de los 24 minutos con estados de render.
- Pistas Global visibles en la timeline del minuto.
- *Resultado:* edición visual completa de un minuto.

**E13. Taller**
- Vista de Brutos, mini-timeline de la Pieza, horneado, ida y vuelta con el minuto.
- *Resultado:* preparar material antes de la timeline.

**E14. Inspector, keyframes y editor de curvas**
- Inspector de propiedades; keyframes en precisión de fotograma; curvas bezier.
- *Resultado:* animación completa de posición, escala, rotación y opacidad.

### Fase E — Capacidades creativas

**E15. Efectos, transiciones y texto**
- Color (brillo, contraste, saturación, temperatura, LUT `.cube`), desenfoque, nitidez, croma.
- Transiciones: fundido, deslizamiento, zoom, barrido.
- Títulos y subtítulos con estilos y animaciones de entrada y salida.
- Velocidad: cámara lenta, rápida, reversa, rampas.

**E16. Audio**
- Volumen, paneo, fundidos, mezcla de capas y Global, reducción automática de la música cuando hay voz.

**E17. Cola de render y exportación**
- `cola_render` en la interfaz, perfiles de exportación, H.265 / 10 bits, codificación por hardware.

### Fase F — Cierre

**E18. Extras**
- Autosave (cada 120 s), atajos de teclado configurables, plugins, formatos de lienzo adicionales (9:16, 1:1, 4:5), subtítulos automáticos.

**E19. Limpieza**
- Eliminar `qwen_video_editor/` y `deep_video_editor/`.
- README final.

### Resumen de dependencias

```
E0 → E1 → E2 → E3 → E4 → E5
                 └──────────→ E6 → E7 → E8 → E9
                                              └→ E10 → E11 → E12 → E13 → E14
                                                                          └→ E15 → E16 → E17 → E18 → E19
```

---

## 18. Especificaciones aspirables

Metas a validar con prototipos, no garantías.

| Aspecto | Objetivo |
|---|---|
| Banco al importar | Más rápido que el tiempo real |
| Scrubbing | < 50 ms |
| Vista previa en vivo (nivel 2) | 256×144 a 640×360 · 10–15 fps · 3–4 capas de video · audio sincronizado |
| Vista previa fluida (nivel 3) | 960×540 (hasta 1280×720) · 24 fps |
| Re-render de un minuto (vista previa) | Segundos, según el equipo |
| Fotograma exacto en pausa | Resolución del monitor · ~150–300 ms |
| Timeline | 200–300 Elementos fluidos, dibujando solo lo visible |
| Render final | 720p por defecto, hasta 4K · H.264 / H.265 · por hardware si hay GPU |
| Deshacer | 100 pasos |
| Autosave | Cada 120 s |
| Plataformas | Windows, macOS, Linux |

---

## 19. Riesgos y preguntas abiertas

| Riesgo | Mitigación |
|---|---|
| Rendimiento del nivel 2 en Flet | Validar en E6/E9; bajar resolución o fps del banco; alternativa PySide6 sobre el mismo `core/` |
| Alfa en VP9 `.webm` | Preferir ProRes 4444 para Piezas con alfa |
| Renombres en Windows con archivos abiertos | Liberar recursos antes de reconciliar; reintentos; diario |
| Rutas largas en Windows (260 caracteres) | Nombres descriptivos cortos; advertencia al superar un umbral |
| Concatenación sin recodificar | Mismos parámetros de codificación y fotograma clave al inicio de cada minuto |
| API de Flet cambiante (0.x) | Fijar versión en `requirements.txt`; aislar Flet en `app/ui` |

Preguntas abiertas:

1. ¿Capítulos siempre de hasta 24 minutos o con duración variable (por ejemplo 22–26)?
2. ¿Se necesita 30 fps además de 24? Cambiaría el rango `f00`–`f29`.
3. ¿Formatos de lienzo verticales (9:16) desde el inicio o en E18?
4. ¿Versión web o móvil de la interfaz en el alcance?
