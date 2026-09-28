# PROJECT.md — Editor de video por capítulos y minutos

Documento maestro de arquitectura. Recoge el enfoque, las decisiones y las
épicas acordadas. Es la referencia única: si el código contradice este
documento, se corrige uno de los dos de forma explícita.

- **Estado:** revisión 12. Fases A–F (E0–E20) implementadas. Siguiente: **Fase G — Entrega (E21 Render y exportación)**. Instalación y uso: [README.md](README.md).
- **Plataforma:** solo Linux. Desarrollo y ejecución desde PyCharm.
- **Punto de partida:** los andamiajes vacíos `qwen_video_editor/` y
  `deep_video_editor/`, que se unifican en una sola arquitectura: `editor/`.
- **Modo de trabajo:** solo código. Sin tests ni pruebas automatizadas por ahora.
  Un único punto de entrada: `main.py`.

---

## Índice

0. [Cambios de las revisiones 2 a 12](#0-cambios-de-las-revisiones-2-a-12)
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
22. [Contratos de integración núcleo ↔ pantallas](#22-contratos-de-integración-núcleo--pantallas)
23. [Casos de uso futuros contemplados](#23-casos-de-uso-futuros-contemplados)
24. [Funciones tomadas de editores equivalentes](#24-funciones-tomadas-de-editores-equivalentes)

---

## 0. Cambios de las revisiones 2 a 12

### Revisión 12: Fase F (capacidades creativas) implementada

| Área | Qué hay | Dónde |
|---|---|---|
| Rampas de velocidad | Keyframes de `velocidad` (0,05×–8×, no en reversa ni congelado); la fuente avanzada es la integral (trapecio, en caché); recortes y ripple la respetan | `modelo/elemento.py`, `comandos/agregar_keyframe.py` |
| Conservar el tono | WSOLA entre 0,5× y 2× (fuera: remuestreo); velocidad constante en la mezcla y `AudioConformado.CONSERVAR_TONO` (por defecto al crear Piezas) | `motor/estiramiento.py`, `mezclador_audio.py`, `horneado.py` |
| Tramos de otro aspecto | Se encajan con bandas al hornear | `servicios/horneado.py` |
| Efectos | Máscara (elipse o rectángulo, suavidad, invertir) y Viñeta; curvas de parámetros de efecto en el editor de curvas | `modelo/efecto.py`, `motor/efectos`, `ui/editor_curvas.py` |
| Transiciones | Fundido a negro (el saliente se oscurece y desaparece a la mitad) | `modelo/transicion.py`, `motor/compositor.py` |
| Presets | Ken Burns, animaciones de entrada/salida (fundido, deslizar, zoom), estabilizar (flujo óptico LK + afín parcial, suavizado; ≤ 60 s) | `comandos/presets.py`, `controladores/creativo.py` |
| Texto | Plantillas título, rótulo, subtítulo y créditos; capas T con idioma solo se ven al ver ese idioma | `modelo/plantillas_texto.py`, `modelo/capitulo.py` |
| Subtítulos | Importar `.srt` (una línea = un texto, sin solapes) y exportar desde una capa T | `servicios/subtitulos.py` |
| Monitores de señal | Medidores de nivel por canal, histograma RGB, forma de onda de luminancia | `ui/monitor.py` |
| Audio | Bajar la música con la voz (keyframes de volumen, un paso de deshacer), sonoridad BS.1770 (ponderación K por bloque, puertas), normalizar a −14 LUFS con techo −1 dBFS, reducción de ruido espectral | `servicios/analisis.py`, `audio_procesado.py`, `render.py`, `controladores/audio.py` |

**Limitaciones conocidas** (se resuelven en E21):

- Los subtítulos de capas T con idioma no se queman en el video común; E21 los exporta como `.srt` o los quema por idioma.
- La huella del video incluye los textos de idioma: cambiarlos provoca un re-render extra, que es inofensivo.
- Las rampas de velocidad cambian el tono del audio (el WSOLA se aplica solo a velocidad constante).
- La normalización se hace por rango renderizado y por pista de idioma.

### Revisión 11: Fase E (completar la edición) implementada

**Regla nueva: un solo capítulo en memoria.** El capítulo es la unidad de trabajo;
cambiar de capítulo es cerrar uno y abrir otro:

| Aspecto | Comportamiento |
|---|---|
| Cambiar o crear capítulo con cambios | Diálogo "Guardar y continuar" / "Cancelar" |
| Al cambiar | Se descarga el anterior (y sus Elementos salen del índice de referencias), el historial empieza vacío, el portapapeles se vacía |
| "¿Algo depende de esto?" en capítulos no cargados | Se lee del disco sin armar el modelo (`proyecto_fs/consultas.py`: fuentes de los gemelos, idiomas de `_capitulo.json`); lo no cargado siempre está guardado |
| Autosave | Solo el capítulo cargado (el único que puede tener cambios) |
| `mover_entre_capitulos` | Queda en el núcleo pero la interfaz no lo usa (dos capítulos a la vez) |

**E17 — Timeline y Taller completos**

| Qué | Dónde |
|---|---|
| Mover en grupo con la selección múltiple (un paso de deshacer, imán en el arrastrado) | `MoverElementos`; `controladores/timeline.arrastrar(..., originales_grupo)` |
| Miniaturas en pistas V y forma de onda en pistas A (se generan si faltan) | `ui/pistas_medios.py`; `preparar_vista_previa` ahora sirve también a audios e imágenes |
| Línea de volumen en las pistas A; **Alt + arrastrar** la mueve (keyframe en el cabezal si el volumen está animado) | `timeline.fijar_volumen` |
| Transiciones visibles (triángulo al comienzo del Elemento) y editables en el inspector | `DescriptorTransicion`, `timeline.cambiar_transicion` |
| Capa destino de audio (A1…) | `EstadoApp.capa_destino_audio` |
| Buscar Elementos por nombre (Ctrl+F; Enter = siguiente) | `timeline.buscar` |
| Taller: buscar escenas y silencios (marcas en las que se hace clic) | `servicios/analisis.py` |
| Taller: alinear un audio externo con el sonido del Elemento elegido | `analisis.desfase` (envolventes a 1 kHz, FFT); `taller.sincronizar_audio` |

**E18 — Proyecto, idiomas y mantenimiento** (menú ☰ Proyecto)

| Qué | Dónde |
|---|---|
| Idiomas del proyecto (el primero es el principal); no se quita uno en uso | `comandos/proyecto.CambiarIdiomas` |
| Atajos editables (solo se guardan los distintos de fábrica; se rechazan repetidos) | `teclado.guardar_atajos`, `ui/dialogos_proyecto.py` |
| Mantenimiento: tamaños, vaciar caché (con la cola quieta), vaciar papelera (tras guardar; olvida el historial), quitar Brutos sin uso | `servicios/mantenimiento.py` |
| Espacio en disco antes de hornear y renderizar (importar ya lo hacía) | `mantenimiento.comprobar_espacio` |

**Corregido**: crear un capítulo escribía `_proyecto.json` sin registrarlo y el
siguiente guardado lo veía como "modificado fuera del programa"
(`registrar_manifiesto_proyecto`).

**Verificado** (recorrido temporal fuera del repositorio): cortes de escena exactos
(45 y 100 en un video de prueba), silencio de 3,0–5,0 s, desfase de +1,50 s con 94 %
de confianza, mover en grupo fusionado y deshecho, idiomas, búsqueda, volumen,
transición, regla de un capítulo, dependencias leídas del disco, espacio en disco.

**Pendiente de E17/E18 que pasa a épicas posteriores**: recortar en grupo (E24,
junto con el rendimiento de la timeline); ajuste por tramo con relaciones de
aspecto distintas en una Pieza (E19).


### Revisión 10: orden de las épicas pendientes y guía de instalación en el README

- Las épicas pendientes se reordenan de abajo hacia arriba: **Fase E Completar la
  edición (E17–E18)**, **F Capacidades creativas (E19–E20)**, **G Entrega
  (E21–E22)**, **H Extensión y cierre (E23–E24)**. Equivalencias con la numeración
  anterior en la sección 19. El código se actualizó a la numeración nueva.
- La guía de instalación pasa al **README** (un solo documento de uso);
  `PROJECT.md` sigue siendo la referencia de arquitectura.
- **Siguiente: E17 — Timeline y Taller completos.**


### Revisión 9: consolidación de A–D antes de la Fase E

Todo el código es Python; la interfaz usa **Flet** (paquetes de `requirements.txt`).

**Cabos sueltos encontrados y cerrados**

| Hallazgo | Corrección |
|---|---|
| Tras restaurar un autosave el historial decía "sin cambios": cerrar sin guardar perdía lo recuperado | `Historial.marcar_sin_guardar()` al restaurar |
| "Descartar" al cerrar dejaba la instantánea y el proyecto volvía a ofrecerla | Descartar borra la instantánea |
| En solo lectura se podía importar, hornear y renderizar (escriben en el proyecto) | Bloqueados con aviso |
| No había forma de poner o pasar Elementos a Global (música, logo fijo) | Comando `CambiarAGlobal` (guardar mueve gemelo y archivo); casilla **Global** en la barra de la timeline; botón en el inspector |
| `QuitarBruto` permitía quitar un Bruto usado por Piezas (el horneado fallaría) | Rechazado; botón **Quitar Bruto** en el Taller |
| Los efectos no declaraban parámetros: la interfaz no podía agregarlos ni editarlos | `DescriptorEfecto` / `Parametro` en `modelo/efecto.py` (rango, valor inicial, unidad, opciones), `efecto_nuevo`, `registrar_efecto(tipo, aplicador, descriptor)`; `CambiarOpcionEfecto`; inspector con pila de efectos (agregar, activar, subir, quitar, parámetros con keyframes, opciones) |
| Deshacer un paso de otro capítulo lo cambiaba sin mostrarlo | Deshacer y rehacer llevan al capítulo afectado |
| Con el botón de reproducir enfocado, Espacio llegaba dos veces | Dos pulsaciones en < 0,25 s cuentan como una |
| Un clic simple también inicia un arrastre: Shift+clic no sumaba a la selección y un clic podía dejar un paso vacío | El arrastre respeta Shift y no ejecuta nada sin desplazamiento |

Verificado fuera del repositorio: recorrido del núcleo (Global ida y vuelta con
guardado y reapertura, efecto animado compuesto al fotograma, `QuitarBruto`
protegido, deshacer entre capítulos, autosave restaurado) y Chromium (Global,
inspector de efectos, Shift+clic).

**Contratos que la Fase E debe respetar** (cómo se conecta con A–D)

| Tema | Regla |
|---|---|
| Ediciones | Siempre un comando por el historial (`Sesion.ejecutar`), nunca tocar el modelo desde la interfaz; valores absolutos para que los arrastres se fusionen |
| Trabajo pesado | Tarea en la cola con instantánea (`Capitulo.instantanea`) y `al_terminar` por `Sesion.tarea` (llega al hilo de Flet) |
| Estado automático | Lo que produce un servicio (render de Shorts, análisis, sonoridad medida) se escribe con `proyecto_fs/automatico.py` y no se deshace |
| Tipos ampliables | Efectos por descriptor; transiciones, animaciones de texto y exportadores deben seguir el mismo patrón (descriptor + registro) para que la interfaz y los plugins (E21) los traten igual |
| Interfaz | Paneles con `.control` y `.refrescar()`, redibujo pedido con `Ventana.refrescar(partes)`; `widgets.actualizar()` para controles que pueden no estar montados |
| Huellas | Todo parámetro nuevo que cambie la imagen o el sonido debe entrar en `serializacion` (y por tanto en la huella del minuto) para invalidar renders y pre-renders |

**Ajustes al plan**: incorporados en el nuevo orden de la revisión 10 (sección 19).

### Revisión 8: Fase D (interfaz) implementada

**Auditoría previa (Fases A–C frente a la interfaz)**

| Hallazgo | Corrección |
|---|---|
| Copiar el capítulo entero para cada imagen del monitor cuesta ~92 ms con 864 Elementos | `Capitulo.instantanea(inicio, fin)`: copia solo lo que toca ese rango (22.8) |
| Los constructores de comandos validan con `ValueError` antes de llegar al historial | `Sesion.ejecutar` acepta también una función que construye el comando y avisa del error |
| `pegar` tenía una línea sin efecto | Quitada |
| Los archivos escritos de forma atómica quedaban con permisos 0600 (`mkstemp`) | Ahora respetan la `umask` (0644 habitual) |
| `ft.app` en 15.2 | `ft.run` (Flet 1.0) |

**Qué se implementó** (`editor/app/`)

| Módulo | Contenido |
|---|---|
| `aplicacion.py` | `lanzar()` para `main.py`; inicio ↔ proyecto; abrir con bloqueo (solo lectura), restaurar autosave, crear; diálogos; cierre de la ventana con `prevent_close`; si la conexión se corta, instantánea de autosave y liberar la sesión |
| `estado.py` | `EstadoApp` (con marcas I/O), `Sesion`, `hacer_en_principal` |
| `controladores/` | `proyecto`, `medios`, `taller` (+ visor de fotogramas nativos), `timeline` (+ quitar rango I–O, añadir texto), `reproduccion`, `render` |
| `ui/ventana.py` | Secciones con `Divisor`, 5 espacios de trabajo, redibujado agrupado (uno por cuadro), bus → paneles, atajos, guardar con conflictos, cerrar con cambios, autosave cada 10 s, pre-render del minuto tras 3 s sin editar |
| `ui/monitor.py` + `asas.py` | Niveles 2 y 4 con imagen y nivel 3 con `Video`; reloj de audio; asas (mover, escalar, girar, ancla), imán a bordes, centro, márgenes y otros Elementos; márgenes seguros; guía 9:16; zoom; Alt + flechas |
| `ui/timeline.py` | Canvas solo de lo visible, 4 zooms, 6 herramientas, imán, desbordes fantasma, Global con borde violeta, cabeceras (ver, silenciar, solo, bloquear, idioma), marcador, texto, rango I–O, alto de pista |
| `ui/mapa_capitulo.py` | 24 celdas: trabajo, render y vista previa lista; doble clic = listo; clic derecho en dos celdas = intercambiar (con confirmación) |
| `ui/taller.py` | Brutos con fps declarado/medido, visor nativo, entrada/salida, fps interpretado, método, crear Pieza, añadir tramo, hornear, colocar, quitar |
| `ui/inspector.py` + `editor_curvas.py` | Espacio, audio, texto, efectos; rombo de keyframe por propiedad, saltar entre keyframes, curvas (incluida bezier) y mover keyframes; historial |
| `ui/cola_render.py` | Barra de tareas con progreso y cancelar; render de minuto, rango o capítulo (pistas o un archivo por idioma) y entregables |
| `ui/navegador.py`, `inicio.py`, `teclado.py`, `tema.py`, `distribucion.py`, `divisor.py`, `widgets/` | Árbol del proyecto e importar; recientes; atajos por foco; tokens del tema oscuro; espacios guardados en `~/.config/editor/` |

**Verificación** (temporal, fuera del repositorio): la interfaz real se sirvió en
modo web de Flet 1.0.2 y se recorrió con Chromium sin pantalla, sobre un
proyecto creado con los controladores (video de 30 fps, PNG con alfa, WAV).

| Recorrido | Resultado |
|---|---|
| Abrir, distribución, espacios Taller / Minuto / Capítulo / Render | ✅ |
| Cabezal por la regla y con flechas; imagen compuesta en el monitor | ✅ |
| Seleccionar en timeline y monitor; mover con asas (un solo paso de deshacer); Ctrl+Z | ✅ |
| Keyframes con K, mover en otro instante → keyframe; curva visible | ✅ |
| Mover en la timeline, cortar con la cuchilla | ✅ |
| Taller: visor nativo, entrada/salida, crear Pieza | ✅ |
| Guardar (Ctrl+S), render del minuto desde la interfaz (archivo + registro + mapa en verde) | ✅ |
| Nuevo capítulo, marcador, cerrar con cambios → descartar → inicio y bloqueo liberado | ✅ |
| Proyecto abierto por otra sesión → diálogo "solo lectura" | ✅ |

**Corregido al verificar**: el `KeyboardListener` raíz ignora `expand` (la columna
central quedaba sin altura); `update()` de un panel oculto lanzaba error; el clic
en la regla borraba la selección; arrastrar en el monitor sin selección no hacía
nada; el visor del Taller quedaba sin altura; si el video del pre-render no se
reproduce (sin libmpv) el cabezal saltaba un minuto: ahora se sigue en vivo y se
avisa; sin salida de sonido, la posición del audio (que no avanza) frenaba la
imagen: ahora manda el reloj monotónico y las llamadas a `Audio`/`Video` tienen
tiempo máximo.

**Hechos de Flet 1.0.2 comprobados** (fuente y ejecución)

| Hecho | Consecuencia |
|---|---|
| Los manejadores síncronos corren en el bucle de Flet | El modelo se toca desde un solo hilo; `hacer_en_principal` ejecuta directo si ya está en el bucle |
| `page.run_task` es seguro entre hilos; sin conexión falla | Las llamadas tardías de tareas se descartan al cerrar |
| `expand` se ignora dentro de `Stack` y de `KeyboardListener`, y en columnas con scroll | Posicionar (`left/top/right/bottom`) o dar alto fijo |
| `control.page` y `update()` lanzan error si el control no está montado | `widgets.actualizar()` |
| `FilePicker`, `Audio` son servicios: se registran al construirse en el contexto de la página | Se crean una vez al montar |
| `FilePicker` en Linux usa `zenity` | Nueva dependencia de sistema (15.4) |
| `KeyboardEvent` solo informa teclas pulsadas | Shift/Ctrl sostenidos se siguen con `KeyboardListener` (arrastres con Shift) |

**Límites conocidos**

| Límite | Dónde se mejora |
|---|---|
| Espacio Shorts: por ahora monitor con guía 9:16 | E20 |
| Detección de escenas y silencios, sincronía de audio externo en el Taller | E15 (siguiente iteración) |
| El nivel 3 necesita libmpv; sin él se reproduce en vivo (nivel 2) | 15.4 |
| Importar abre el selector del sistema (zenity); arrastrar archivos desde el gestor de archivos no está disponible en Flet de escritorio | — |

### Revisión 7: Fase C (motor y servicios) implementada

**Verificación con medios reales** (sintéticos, fuera del repositorio): video de
30 fps con audio, PNG con transparencia y música WAV.

| Qué se comprobó | Resultado |
|---|---|
| Análisis al importar | 30 fps declarado y medido, sin fps variable, alfa del PNG, duración de la música |
| Horneado 30 → 24 fps | Tramo de 3 s = 72 fotogramas + 24 de asa a cada lado; conformar, mezcla e interpolación también |
| Composición | Exacta al fotograma (se ve el fotograma nativo esperado), escala "llenar", PNG con alfa girado y con opacidad animada, texto con contorno, efecto de saturación |
| Render de un minuto | 1280×720, 24 fps, **1440 fotogramas, 60,00 s**, dos pistas de audio etiquetadas `spa` y `eng` |
| Caché de minutos | Segundo render del mismo minuto: 1,5 s en vez de 26,7 s |
| Vista previa nivel 2 (banco, 256×144) | ~**218 fps** en el contenedor de desarrollo (el objetivo era 10–15) |
| Fotograma exacto 1280×720 (nivel 4) | ~130 ms |
| Cola de tareas | Prioridades, reemplazo por clave, errores informados sin detener la cola |
| `main.py` | `--render` (con `--por-idioma`), `--fotograma`, `--escanear` |

**Corregido durante la implementación**: versiones de render que confundían
"minuto 5" con "rango 5-5"; un render nuevo podía pisar un archivo existente no
registrado; el archivo horneado viejo quedaba huérfano al cambiar de formato;
posición inicial de los textos (ahora en el tercio inferior izquierdo).

**Límites conocidos (para épicas posteriores)**

| Límite | Dónde se mejora |
|---|---|
| Cambiar velocidad o conformar cambia el tono del audio (estiramiento simple) | E18 (estiramiento que conserve el tono) |
| Una Pieza con tramos de distinta relación de aspecto se estira al tamaño del primero | E15 (ajuste por tramo) |
| Sin VAAPI en el PyAV binario | 15.4 (compilar PyAV) |

### Revisión 6: auditoría de la Fase B e integración con la Fase C

Se ejecutó un recorrido temporal (fuera del repositorio) con **todos los comandos**,
guardado, deshacer y rehacer de 43 pasos, reapertura y casos límite.

**Errores reales corregidos**

| # | Hallazgo | Corrección |
|---|---|---|
| B1 | El estado automático (renders, horneado) estaba mezclado con lo que edita el usuario: un render se perdía al cerrar sin guardar, o guardarlo persistía ediciones no deseadas | Archivos propios: `render/_renders.json` y `_horneado.json`, escritos en el momento por `proyecto_fs/automatico.py` (22.7) |
| B2 | Una Pieza horneada y renombrada antes del primer guardado perdía su carpeta y su horneado | El reconciliador localiza la carpeta real por receta, `_horneado.json` o archivo horneado |
| B3 | Las copias hacia los minutos buscaban el horneado en la ruta vieja cuando la carpeta de la Pieza se movía en el mismo guardado | Se copia desde la ruta final (las copias van después de los movimientos) |
| B4 | Un paso del diario que fallaba dejaba el plan trabado para siempre | El paso se registra como error y se sigue; `ResultadoGuardado.errores` |
| B5 | Deshacer y rehacer "crear Pieza" perdía su horneado | Los comandos del Taller conservan siempre el horneado vigente |
| B6 | Deshacer podía devolver a un Elemento una versión de Pieza cuyo archivo ya no existe | `sincronizar_con_fuente` al restaurar |
| B7 | Importar o hornear sin guardar dejaba archivos huérfanos invisibles | El escáner los informa (`brutos_sin_registrar`, `taller_sin_receta`) |
| B8 | Los nombres de render no admitían idioma | `cap0001_completo_v002_en.mp4` y Shorts `…_v001_es.mp4` |
| B9 | Los tipos de efecto y transición eran listas fijas: los plugins no podrían agregar | Registros ampliables (`registrar_tipo_efecto`, `registrar_tipo_transicion`) |
| B10 | El compositor no tenía cómo saber qué transición está en curso | `Capitulo.transiciones_activas(f)` con saliente, entrante y progreso |

Verificadas como **reglas correctas** (no errores): roll sin material de fuente,
cambios sobre capas bloqueadas y solapes se rechazan sin tocar el modelo.

### Revisión 5: versiones, pistas de idioma y funciones de otros editores

| # | Cambio | Sección |
|---|---|---|
| V1 | **Flet 1.0.2** en los cuatro paquetes (`flet`, `flet-desktop` vía el extra, `flet-video`, `flet-audio`); APIs verificadas iguales que en 1.0.1 | 17 |
| V2 | **Python 3.13 recomendado** (mínimo 3.12) | 15.4 |
| V3 | **Pistas de idioma**: cada capa A puede tener idioma; la pista común (música y efectos) suena en todos; render con varias pistas de audio o un archivo por idioma; subtítulos por idioma | 13.6 |
| V4 | Funciones de Premiere, DaVinci Resolve, Final Cut, CapCut, Kdenlive y Shotcut repartidas en las épicas | 24 |

### Revisión 4: auditoría de integración

Revisión completa del código de la Fase A y de las dependencias reales.

**Corregido en el código**

| # | Hallazgo | Corrección |
|---|---|---|
| A1 | Una animación de escala que cruza el cero (volteo de 1 a −1) hacía fallar la evaluación del Elemento | `Transform.con_valores` limita la escala a ±0,0001 |
| A2 | Orden de apilado ambiguo entre Global y los minutos (ambos V1) | Orden fijo: V del minuto → V de Global → T del minuto → T de Global (`Capa.orden_apilado`) |
| A3 | Con IDs de 4 hexadecimales caben 65 536 objetos; 1000 capítulos llenos los superan | **IDs de 6 hexadecimales** (16,7 millones) |
| A4 | Los eventos de edición no decían qué minutos redibujar e invalidar (un Elemento movido o que se desborda toca varios) | `ElementoCambiado` lleva `minutos_afectados`; nuevos `ElementoAgregado`, `CapituloCreado`, `PiezaModificada`, `TareaProgreso`, `TareaTerminada` |
| A5 | El Elemento no sabía cuánto material tiene su fuente: trim y slip podían pedir fotogramas inexistentes | `TiempoElemento.fuente_duracion`, `excede_fuente`, `margen_fuente` |
| A6 | Abrir un proyecto obligaba a cargar los 1000 capítulos | **Carga perezosa**: `Proyecto.indice_capitulos` + `cargador_capitulo` inyectado por `proyecto_fs` (sin romper la dirección de dependencias) |
| A7 | Faltaban marcadores y estado por capa (ocultar, silenciar, bloquear, solo) | `modelo/marcador.py`; `Capitulo.marcadores`, `Capitulo.capas`, `se_ve`, `se_oye`, `editable` |
| A8 | `flet==1.0.1` sin el extra `desktop` no abre ventana | `flet[desktop]==1.0.1` |
| A9 | Nada reproducía audio: el reloj maestro del nivel 2 no tenía base | `flet-audio==1.0.1` (misma versión que `flet` y `flet-video`) |
| A10 | Faltaban constantes para papelera, bloqueo y versión de esquema | `CARPETA_PAPELERA`, `ARCHIVO_BLOQUEO`, `VERSION_ESQUEMA` |

**Verificado en las dependencias**

| Qué | Resultado |
|---|---|
| Códecs de PyAV 18.1.0 | ✅ `libx264`, `libx265`, `prores_ks`, `libvpx-vp9` (alfa), `png`, `libwebp`, `aac`, `qtrle`, NVENC. ❌ VAAPI (15.4) |
| Flet 1.0.1 | ✅ `ft.run`, `Image(src=bytes)`, `page.run_task` / `run_thread`, `on_keyboard_event`, `canvas`, `GestureDetector`, `Video` con lista de reproducción, `Audio`. Los métodos de medios son **asíncronos** (22.4) |

**Agregado al plan**

| # | Cabo suelto | Resolución | Dónde |
|---|---|---|---|
| P1 | Un intercambio de nombres A↔B podía pisar archivos | Renombres en dos fases | T5.8 |
| P2 | Deshacer un borrado después de guardar | `.papelera/` | T5.9 |
| P3 | Dos instancias abriendo el mismo proyecto | `.bloqueo` | T5.5 |
| P4 | Archivos cambiados fuera del programa | Firma + conflicto, nunca sobrescribir | T5.8 |
| P5 | Volver a hornear una Pieza con copias en capítulos no cargados | Lista de copias en `_pieza.json` | T5.2 |
| P6 | Materializar requiere el motor (extraer audio, normalizar imágenes) y el reconciliador no puede usarlo | La materialización la ejecuta el servicio de guardado (N4) | T9.5 |
| P7 | Qué archivo lee el motor si la copia aún no se guardó | Resolución de fuente: copia → horneado → Bruto → fuera de línea | T9.2 |
| P8 | Trim de entrada y división con keyframes relativos | Los comandos desplazan y reparten keyframes | T6.4 |
| P9 | Estado de la interfaz mezclado con el modelo | `EstadoApp` separado, no se deshace | 22.1 |
| P10 | Atajos que chocan con campos de texto | Contextos de foco | T12.7 |
| P11 | Formatos de proyecto futuros | `version_esquema` en `_proyecto.json` | T5.2 |
| P12 | Exportar un fotograma (miniaturas) | Función y modo de `main.py` | T7.8 |

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
5. **IDs**: 6 caracteres hexadecimales, **únicos en todo el proyecto**
   (Brutos, Piezas y Elementos comparten el mismo espacio de IDs). Nunca
   cambian.
6. **Nombre descriptivo**: minúsculas, números y guiones; máximo 32 caracteres.
7. **Capítulos**: `cap0001` a `cap1000`, siempre con 4 dígitos. En pantalla se
   muestra sin ceros: "Capítulo 1". El título libre va en `_capitulo.json`.

### 3.3 Gramática del nombre de un Elemento

```
min02_seg12f08_dur05s00_V2_puerta-abre__a3f90e.mov
 │     │    │    │        │   │            │      │
 │     │    │    │        │   │            │      └ extensión (.mov si tiene alfa)
 │     │    │    │        │   │            └ ID del Elemento (6 hexadecimales)
 │     │    │    │        │   └ nombre descriptivo
 │     │    │    │        └ capa: V video/imagen · A audio · T texto (1–9)
 │     │    │    └ duración: segundos + fotogramas (dur01m05s00 si ≥ 1 min)
 │     │    └ fotograma de inicio (f00–f23)
 │     └ segundo de inicio (seg00–seg59)
 └ minuto de inicio (min00–min23)
```

Expresión regular de referencia:

```
^min(\d{2})_seg(\d{2})f(\d{2})_dur(?:(\d{2})m)?(\d{2})s(\d{2})_([VAT][1-9])_([a-z0-9-]{1,32})__([0-9a-f]{6})\.(\w+)$
```

Otros nombres:

| Objeto | Formato | Ejemplo |
|---|---|---|
| Bruto | `bruNNNN_nombre__id.ext` | `bru0001_toma-calle__7c2185.mp4` |
| Pieza (carpeta y archivo) | `pieNNNN_nombre__id` | `pie0001_puerta-abre__5e1c3a.mov` |
| Render de un minuto | `capCCCC_minMM_vNNN.mp4` | `cap0001_min00_v003.mp4` |
| Render de un rango | `capCCCC_minMM-MM_vNNN.mp4` | `cap0001_min05-08_v001.mp4` |
| Render del capítulo | `capCCCC_completo_vNNN.mp4` | `cap0001_completo_v002.mp4` |
| Short (receta) | `minMM_segSSfFF_dur…_nombre__id.json` | `min02_seg10f00_dur45s00_momento-clave__b71c4d.json` |
| Short (render) | igual que la receta + `_vNNN.mp4` | `min02_seg10f00_dur45s00_momento-clave__b71c4d_v001.mp4` |

Un Short usa la misma gramática que un Elemento **sin el campo de capa**: el
nombre dice en qué instante del capítulo empieza y cuánto dura.

### 3.4 Convenciones de código

| Aspecto | Convención |
|---|---|
| Python | 3.13 recomendado (mínimo 3.12), con anotaciones de tipo |
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
min02_seg12f08_dur05s00_V2_puerta-abre__a3f90e.mov    ← contenido
min02_seg12f08_dur05s00_V2_puerta-abre__a3f90e.json   ← gemelo
```

```json
{
  "id": "a3f90e",
  "fuente": { "tipo": "pieza", "ref": "5e1c3a", "version": 3 },
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
min02_seg14f00_dur03s00_T1_titulo-capitulo__d4e25c.json
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
│   ├── video/   bru0001_toma-calle__7c2185.mp4
│   ├── audio/   bru0002_entrevista__91be07.wav
│   └── imagen/  bru0003_logo__0f3a6b.png
├── taller/                                 T1 · sandbox
│   └── pie0001_puerta-abre__5e1c3a/
│       ├── _pieza.json                     receta + copias (lo que edita el usuario)
│       ├── _horneado.json                  estado automático: resultado del horneado
│       └── pie0001_puerta-abre__5e1c3a.mov   horneado normalizado (.mp4 si es opaco)
├── recursos/
│   ├── fuentes/                            .ttf / .otf usados por los textos
│   └── luts/                               .cube
├── cap0001/                                  ← CAPÍTULO
│   ├── _capitulo.json                      título, duración, registro de renders
│   ├── global/
│   │   ├── min00_seg00f00_dur24m00s00_A1_musica-tema__c810f2.wav
│   │   └── min00_seg00f00_dur24m00s00_A1_musica-tema__c810f2.json
│   ├── min00/                              ← MINUTO 00:00–00:59
│   │   ├── _minuto.json
│   │   ├── _guion.txt
│   │   ├── min00_seg00f00_dur12s08_V1_ciudad-amanece__4b7e19.mp4
│   │   ├── min00_seg00f00_dur12s08_V1_ciudad-amanece__4b7e19.json
│   │   ├── min00_seg12f08_dur05s00_V2_puerta-abre__a3f90e.mov
│   │   ├── min00_seg12f08_dur05s00_V2_puerta-abre__a3f90e.json
│   │   └── min00_seg14f00_dur03s00_T1_titulo-capitulo__d4e25c.json
│   ├── min01/ … min23/
│   ├── render/
│   │   ├── _renders.json                   estado automático: entregables y últimos renders
│   │   ├── cap0001_min00_v003.mp4
│   │   ├── cap0001_completo_v002.mp4
│   │   └── cap0001_completo_v002_en.mp4    versión por idioma
│   └── shorts/                             ← recortes verticales 9:16
│       ├── min02_seg10f00_dur45s00_momento-clave__b71c4d.json       receta
│       └── min02_seg10f00_dur45s00_momento-clave__b71c4d_v001.mp4   720×1280
├── cap0002/ … cap1000/
├── .bloqueo                                PID, equipo y fecha de la instancia que lo tiene abierto
├── .diario/                                operaciones de disco pendientes
├── .papelera/                              lo borrado, con su ruta original
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
| Intercambio de nombres (A↔B) | Renombres en dos fases con nombres temporales |
| Deshacer un borrado ya guardado | Lo borrado va a `.papelera/` y el siguiente guardado lo recupera |
| Dos instancias sobre el mismo proyecto | `.bloqueo`; la segunda abre en solo lectura |
| Cambios hechos fuera del programa | Firma distinta = conflicto; se avisa y no se sobrescribe |

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
5. Codificación por hardware: **NVENC** (NVIDIA) viene incluido en PyAV. **VAAPI**
   (Intel/AMD) no viene en el paquete binario de PyAV: requiere compilar PyAV contra
   el FFmpeg del sistema (15.4). Sin aceleración, `libx264` por software.
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
  "id": "b71c4d",
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

### 13.6 Pistas de idioma

Modelo profesional de doblaje: **diálogo por idioma + pista común**.

| Capa A | `idioma` | Suena en |
|---|---|---|
| Música, efectos, ambiente | vacío (común) | Todas las versiones |
| Diálogo en español | `es` | Versión `es` |
| Diálogo en inglés | `en` | Versión `en` |

- El idioma se asigna **por capa** del capítulo (`EstadoCapa.idioma`), para minutos y para Global (`GA1`, `GA2`…). Así "A1 = español, A2 = inglés" vale para los 24 minutos.
- El proyecto declara sus idiomas (`Proyecto.idiomas`); el primero es el **principal**.
- **Edición y vista previa**: se escucha el idioma elegido en el transporte (por defecto el principal) más la pista común. Cambiar de idioma no toca el modelo; es estado de la app.
- **Mezcla** (E8): `Capitulo.sonoros_activos_en(f, idioma)` devuelve lo común más ese idioma.
- **Render** (E10), a elegir en el perfil:
  - **Un archivo con varias pistas de audio** (una por idioma, con su etiqueta de idioma en los metadatos); el video se codifica una sola vez.
  - **Un archivo por idioma**: `cap0001_completo_v002_es.mp4`, `cap0001_completo_v002_en.mp4`.
  - **Solo audio por idioma** (WAV o AAC), para entregar a plataformas.
- **Subtítulos por idioma**: capas T marcadas con idioma, exportables a `.srt` y como pista de subtítulos dentro del MP4 (sin quemar en la imagen), o quemados si se prefiere.
- **Shorts**: se renderizan en el idioma principal o en todos.
- **Huellas**: el audio de cada idioma tiene su propia huella; cambiar el diálogo en inglés no invalida la versión en español.

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
| `ElementoAgregado` / `ElementoCambiado` / `ElementoQuitado` | historial (tras un comando), con `minutos_afectados` | timeline, inspector, monitor, selección, huellas |
| `HistorialCambiado` | historial | menú Editar, barra de estado |
| `CapituloCreado` | servicio de proyecto | navegador |
| `PiezaModificada` | comandos del Taller | Taller (marca "sin hornear") |
| `TareaProgreso` / `TareaTerminada` | cola de tareas | barra de estado, cola de render |
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
  7a. Modo interfaz: ft.run(...) → app/aplicacion.py (sin ruta: último proyecto o inicio)
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

- **Python 3.13 recomendado** (mínimo 3.12, lo exige numpy 2.5; 3.14 también tiene paquetes de todas las dependencias) en un entorno virtual (`.venv/`) creado desde PyCharm.
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
| `fonts-dejavu` o similares | Fuentes por defecto para los textos y la interfaz |
| `zenity` | Selector de archivos y carpetas de Flet (importar, abrir, nuevo proyecto) |

PyAV 18.1.0 trae FFmpeg dentro de su paquete. **Verificado** (revisión 4): incluye
`libx264`, `libx265`, `prores_ks` (codificar ProRes 4444), `prores`, `libvpx-vp9`
(decodificar VP9 con alfa), `png`, `mjpeg`, `libwebp`, `aac`, `pcm_s16le`, `qtrle`
y `h264_nvenc` / `hevc_nvenc`. **No** incluye VAAPI; para usarlo:
`sudo apt install libavcodec-dev libavformat-dev libavdevice-dev libavfilter-dev libswscale-dev libswresample-dev`
y `pip install av==18.1.0 --no-binary av` (usa el FFmpeg del sistema).

Flet 1.0 necesita el extra `desktop` (`flet[desktop]`) para abrir la ventana de
escritorio; ya está en `requirements.txt`. `flet`, `flet-desktop`, `flet-video` y
`flet-audio` se publican juntos y cada uno exige la misma versión exacta de `flet`:
al actualizar, se cambian los cuatro a la vez.

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
- Alt + flechas = 1 px, Alt + Shift + flechas = 10 px (las flechas solas avanzan fotogramas).
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

### 16.6 Gestos y atajos (revisión 8)

| Dónde | Gesto | Acción |
|---|---|---|
| Regla de la timeline | Clic / arrastrar | Mover el cabezal (no cambia la selección) |
| Elemento en la timeline | Clic (Shift: sumar) · arrastrar el cuerpo o un borde | Seleccionar · mover, recortar, ripple, roll, slip o slide según la herramienta |
| Elemento en la timeline | Doble clic | Abrir su Pieza en el Taller |
| Timeline | Rueda (Ctrl: zoom) | Desplazar en los zooms de segundos y fotograma |
| Monitor | Clic · arrastrar | Seleccionar lo de arriba · mover (o la asa: escalar, girar, ancla; Shift = libre) |
| Mapa | Clic · doble clic · clic derecho en dos celdas | Ir al minuto · marcar listo · intercambiar minutos |
| Divisores | Arrastrar · doble clic | Cambiar tamaño · plegar |

Atajos (`config/atajos.json`; el usuario los redefine en `~/.config/editor/atajos.json`):
Espacio y L reproducir/pausar · ← → fotograma (en el Taller, fotograma nativo) ·
Shift + ← → y J segundo · Inicio: comienzo del minuto · RePág/AvPág minuto ·
I / O entrada y salida · S dividir · M marcador · V C B N Y U herramientas ·
K keyframe · Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y · Ctrl+S · Ctrl+C / Ctrl+V / Ctrl+D ·
Supr / Shift+Supr (ripple) · = / − zoom · Alt (+ Shift) + flechas: 1 (10) px · Esc
deseleccionar. Con el foco en un campo de texto solo funciona Ctrl+S.

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
    │   ├── ajustes.py                   N0 · ajustes de la aplicación (config/ y ~/.config/editor/)
    │   ├── eventos.py                   N0 · BusEventos y tipos de evento
    │   ├── utiles/                      N0
    │   │   ├── interpolacion.py  matematicas.py  registro.py
    │   ├── tiempo/                      N1
    │   │   ├── granularidad.py          fotograma ↔ (min, seg, f)
    │   │   └── nomenclatura.py          nombres ↔ datos, IDs
    │   ├── espacio/                     N1
    │   │   ├── transform.py  lienzo.py  geometria.py
    │   ├── modelo/                      N2
    │   │   ├── errores.py               ErrorModelo, Solapamiento, NoEncontrado
    │   │   ├── composicion.py           base de Minuto y Global
    │   │   ├── proyecto.py  capitulo.py  minuto.py  global_.py
    │   │   ├── bruto.py  pieza.py  taller.py
    │   │   ├── elemento.py  capa.py  keyframe.py
    │   │   ├── efecto.py  transicion.py  texto.py
    │   │   ├── marcador.py              Marcador, EstadoCapa
    │   │   ├── short.py                 Short + VentanaVertical
    │   │   └── referencias.py           índice Bruto → Pieza → Elemento → Minuto
    │   ├── comandos/                    N3
    │   │   ├── comando.py  compuesto.py  historial.py  operaciones.py  fabrica.py  estado_capitulo.py
    │   │   ├── capas.py  colocacion.py  taller.py
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
    │   │   ├── serializacion.py         conversión canónica (también para huellas)
    │   │   ├── estructura.py  gemelo.py  manifiestos.py  bloqueo.py
    │   │   ├── estado_disco.py          último estado conocido del disco
    │   │   ├── automatico.py            escribe en el momento renders y horneados
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
    │   │   ├── fuentes.py               qué archivo lee el motor para cada Elemento
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
        ├── aplicacion.py                arranque Flet, inicio ↔ proyecto, diálogos, cierre
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
            ├── teclado.py               atajos con contextos de foco
            ├── tema.py                  tokens del tema (recursos/temas/oscuro.json)
            ├── widgets/                 timecode, imagen de relleno, actualizar()
            └── recursos/                iconos, temas
```

`requirements.txt`:

```
flet[desktop]==1.0.2
flet-video==1.0.2
flet-audio==1.0.2
av==18.1.0
numpy==2.5.3
opencv-python-headless==5.0.0.93
Pillow==12.3.0
```

Versiones fijadas en E0. Las dependencias de sistema de Linux están en 15.4.

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

**E5. Disco (N3)** — el proyecto existe en carpetas reales, se guarda, se reabre y se rescata.

| Tarea | Detalle |
|---|---|
| T5.1 Serialización base (`proyecto_fs/serializacion.py`, nuevo) | Conversión canónica (claves ordenadas, sin espacios variables) de: `Fraction` ↔ `"30000/1001"`, Instante ↔ `"min02_seg12f08"`, Duración ↔ `"dur05s00"`, Transform y Recorte, Animación y Keyframe (controles como lista), Efecto, Transición, Texto, enums por su valor. Es la misma serialización que usan las huellas (E10) |
| T5.2 Manifiestos | `_proyecto.json`: `version_esquema`, nombre, estándar, índice de capítulos (número → título), IDs usados, Brutos (datos de análisis y `fps_interpretado`). `_capitulo.json`: título, estado de capas, marcadores, registro de renders. `_minuto.json`: listo, notas, último render. `_pieza.json`: receta, horneado, versión y **lista de copias** (capítulo, minuto, ID) para no cargar capítulos al volver a hornear |
| T5.3 Gemelos | Elemento ↔ JSON según 8.3; Elementos T sin archivo de medios; `fuente_duracion` incluida. Receta de Short ↔ JSON |
| T5.4 Estructura | Crear proyecto (carpetas, `brutos/video|audio|imagen`, `recursos/fuentes|luts`, `_proyecto.json`). Crear capítulo (`min00`–`min23`, `global/`, `render/`, `shorts/`, manifiestos) |
| T5.5 Bloqueo | `.bloqueo` con PID, equipo y fecha. Si otro proceso vivo lo tiene: abrir en solo lectura o cancelar. Bloqueo huérfano (PID muerto): se recupera con aviso |
| T5.6 Escáner y carga perezosa | Abrir = leer `_proyecto.json` y el Taller, e inyectar `Proyecto.cargador_capitulo`. Cargar un capítulo = leer minutos, Global y Shorts. Tolerancias: gemelo faltante → espacio por defecto; gemelo sin archivo → fuera de línea; archivos con nombre no reconocido → lista aparte, nunca se tocan; ID duplicado → se reasigna al guardar, con aviso |
| T5.7 Diario | Operaciones: copiar, mover, renombrar, escribir, enviar a papelera. Plan en `.diario/` con estado por paso y `fsync`. Al abrir, un plan a medias se completa o se revierte |
| T5.8 Reconciliador | Compara el modelo con el **último estado conocido del disco** (lo leído al abrir o escrito al guardar). Genera: copias nuevas a materializar, movimientos, renombres, gemelos y manifiestos a escribir, envíos a `.papelera/`. **Renombres en dos fases** (nombre temporal y después definitivo) para que un intercambio A↔B no pise archivos. Si un archivo cambió fuera del programa (firma distinta): conflicto, no se sobrescribe, se avisa |
| T5.9 Papelera | Lo borrado va a `.papelera/` con su ruta original. Deshacer después de guardar lo recupera en el siguiente guardado. Vaciado manual o por antigüedad |
| T5.10 Guion | `_guion.txt` por minuto, generado al guardar |
| T5.11 Autosave | Instantánea del modelo cargado en `.autosave/` (sin tocar archivos de medios). Al abrir: si es más reciente que el disco, ofrecer restaurarla |
| T5.12 main | `--nuevo` crea y (hasta E12) informa; `--escanear` imprime capítulos, Elementos, fuera de línea, no reconocidos y conflictos |

**E6. Comandos (N3)** — toda la edición con deshacer.

| Tarea | Detalle |
|---|---|
| T6.1 Contrato `Comando` | `ejecutar(proyecto)`, `deshacer(proyecto)`, `descripcion`, `afectados()` → capítulo, IDs y minutos antes y después (desbordes incluidos), `fusionar(otro)` para arrastres continuos. **Valida todo antes de mutar**: nunca deja el modelo a medias |
| T6.2 Historial | Único por proyecto (no por minuto). Límite 100. Marca de "guardado" para saber si hay cambios. Publica `HistorialCambiado`, `ElementoAgregado/Cambiado/Quitado` con `minutos_afectados`, `ProyectoModificado` |
| T6.3 Compuesto | Agrupa comandos; deshace en orden inverso |
| T6.4 Elementos | Agregar desde Pieza (`fuente_entrada` = asas reales, `fuente_duracion`, tamaño, alfa, audio, transform según ajuste inicial, ID nuevo); agregar imagen o audio directo desde Bruto (`fuente_entrada` = 0); quitar; mover (tiempo, capa, minuto, **entre capítulos**); duplicar; pegar (el portapapeles es estado de la app); recortar (trim de entrada **desplaza keyframes** y `fuente_entrada`); dividir (reparte keyframes); separar audio; cambiar velocidad |
| T6.5 Propiedades | Cambiar propiedad genérica, transformar, mover ancla con compensación, keyframes (poner, quitar, mover), efectos (agregar, quitar, reordenar, parámetro), transición, texto |
| T6.6 Edición avanzada | Ripple con alcance minuto o capítulo, roll, slip (limitado por `margen_fuente`), slide. Todos compuestos |
| T6.7 Capas y marcadores | Visible, silenciada, bloqueada, solo; marcadores (poner, mover, quitar) |
| T6.8 Nivel superior | Mover o intercambiar minutos; `actualizar_fuente` tras volver a hornear (versión, `fuente_duracion`, reajuste de `fuente_entrada` si cambiaron las asas); comandos del Taller (agregar Bruto y Pieza, cambiar receta, interpretar fps); Shorts (crear, rango, ventana, keyframes) |
| T6.10 Modos de colocación y rangos | Insertar / sobrescribir / rechazar al colocar o mover; edición de tres puntos; levantar y extraer un rango; cerrar huecos; congelar fotograma (24.1) |
| T6.9 Reglas | Rechazar cambios sobre Elementos o capas bloqueados; rechazar lo que exceda la fuente (`excede_fuente`); el aviso de ripple de capítulo lo pide la app **antes** de ejecutar |

### Fase C — Motor y servicios

**E7. Decodificación y compositor (N3)**

| Tarea | Detalle |
|---|---|
| T7.1 `motor_base` | Interfaz: abrir una ruta → fuente; `fotograma(n, tamaño)` → RGBA premultiplicado (numpy); información de la fuente |
| T7.2 Decodificador | PyAV; búsqueda exacta por PTS (saltar al fotograma clave anterior y decodificar hasta el pedido); reutilizar contenedores abiertos (LRU); formatos con alfa (`yuva420p`, ProRes 4444, RGBA); imágenes con Pillow; decodificar al tamaño necesario |
| T7.3 Caché | LRU por (ruta, firma, fotograma, tamaño) con límite en MB (`Ajustes.cache_fotogramas_mb`) |
| T7.4 Compositor | Recibe los Elementos evaluados de `Capitulo.visuales_activos_en(f)`; fondo negro; descarte, región de interés, `warpAffine`, efectos, modos de mezcla (fórmulas sobre premultiplicado), transiciones (fundido = rampa de opacidad del entrante; deslizamiento, zoom y barrido = transform adicional); salida RGB/RGBA a cualquier escala |
| T7.5 Texto | Pillow dibuja al tamaño del destino (nítido en Shorts y 4K); caché por (contenido, estilo, escala) |
| T7.6 Conversión de fps | Los 5 métodos sobre el flujo de fotogramas nativos; interpolación con flujo óptico de OpenCV |
| T7.7 Codificador | PyAV: video + audio, parámetros del Estandar, fotograma clave en el primer fotograma, NVENC opcional |
| T7.8 Exportar fotograma | Un fotograma del capítulo a PNG (miniaturas de YouTube, revisión). También como modo de `main.py` |

**E8. Mezclador de audio (N3)**

| Tarea | Detalle |
|---|---|
| T8.1 Rejilla exacta | 48 000 / 24 = **2000 muestras por fotograma**: audio y video se alinean sin redondeos |
| T8.2 Mezcla | float32 estéreo; remuestreo de cada fuente a 48 kHz con `av.AudioResampler`; volumen y paneo con rampas por muestra (sin clics); fundidos; transiciones cruzadas cuando dos Elementos se solapan por una transición |
| T8.3 Estados e idiomas | Respeta `Capitulo.se_oye` (silenciar, solo e idioma) y `Elemento.suena`; una mezcla por idioma: pista común + diálogo de ese idioma (13.6) |
| T8.4 Salida | Limitador suave; WAV para vista previa, AAC para el render |

**E9. Cola de tareas y servicios de medios (N4)**

| Tarea | Detalle |
|---|---|
| T9.1 Cola | Hilos de trabajo (`Ajustes.trabajadores_fondo`) con prioridades (14.4), cancelación, reprioridad; cada tarea recibe una **instantánea** (`copy.deepcopy` del subconjunto que necesita) y su huella; publica `TareaProgreso` y `TareaTerminada` |
| T9.2 Resolución de fuente (`servicios/fuentes.py`, nuevo) | Qué archivo se lee para un Elemento: la copia materializada si existe; si todavía no se guardó, el horneado de su Pieza; si es directo, el Bruto; si no hay ninguno, fuera de línea (`MedioFueraDeLinea`) |
| T9.3 Importación | Copiar a `brutos/` con progreso; analizar: flujos, fps declarado, fps medido por marcas de tiempo, fps variable, alfa por formato de píxel, audio; comprobar espacio en disco |
| T9.4 Horneado | Tramos → conversión de fps → transform y efectos de la Pieza → asas → codificar `.mp4` o `.mov`; versión + 1; `PiezaHorneada`; después el comando `actualizar_fuente` para todas sus copias (lista en `_pieza.json`) |
| T9.5 Materialización | La ejecuta el **servicio de guardado** (N4), no el reconciliador, porque puede necesitar el motor: copiar la Pieza, extraer WAV para "separar audio", normalizar imágenes a PNG y audio directo a WAV 48 kHz |
| T9.6 Banco, miniaturas, forma de onda | Según 12.1, con firma para invalidar |

**E10. Render y ensamblado (N4)**

| Tarea | Detalle |
|---|---|
| T10.1 Huellas | Hash de la serialización canónica (T5.1) de todo lo que afecta al minuto (`Capitulo.que_afecta_al_minuto`), firmas de archivos, estado de capas y estándar. Publica `MinutoInvalidado` al cambiar |
| T10.2 Render de minuto | 1440 fotogramas exactos, solo video, fotograma clave inicial, parámetros idénticos entre minutos |
| T10.3 Audio del capítulo | Una pasada del mezclador para el rango pedido |
| T10.4 Ensamblado | Unir minutos **copiando paquetes** con PyAV (sin recodificar) y multiplexar el audio |
| T10.5 Entregables | Minuto, rango, capítulo; por idioma (varias pistas de audio etiquetadas en un archivo, o un archivo por idioma); versionado; registro en `_capitulo.json`; `RenderTerminado`; `main.py --render` |

**E11. Vista previa (N4)**

| Tarea | Detalle |
|---|---|
| T11.1 Niveles 1, 2 y 4 | Imagen JPEG en bytes para `ft.Image(src=bytes)` |
| T11.2 Nivel 3 | Pre-render por minuto en segundo plano; lista de reproducción de minutos para `flet_video.Video` |
| T11.3 Reloj de audio | `flet_audio.Audio` reproduce la mezcla de vista previa. Como `get_current_position()` es asíncrono y tiene latencia, el reloj se **extrapola** con `time.monotonic()` entre consultas y se corrige en cada respuesta |
| T11.4 Guardado | Servicio de guardado (reconciliador + materialización + guion) y autosave conectados a eventos |

### Fase D — Interfaz

**E12. Aplicación base (N5–N6)**

| Tarea | Detalle |
|---|---|
| T12.1 Arranque Flet 1.0 | `ft.run(principal)`; APIs confirmadas en 1.0.1 y 1.0.2: `Image(src=bytes)`, `page.run_task`, `page.run_thread`, `page.on_keyboard_event`, `canvas`, `GestureDetector`, `Video` con lista de reproducción, `Audio` asíncrono |
| T12.2 `EstadoApp` | Estado de la interfaz que **no** es del modelo ni se deshace (sección 22.1) |
| T12.3 Puente de eventos | `app/estado.py` se suscribe al bus; los eventos que llegan desde hilos de trabajo se pasan al bucle de Flet con `page.run_task`; se agrupan para redibujar como máximo una vez por cuadro |
| T12.4 Ventana | Secciones, `Divisor`, distribución y espacios de trabajo (Taller, Minuto, Capítulo, Shorts, Render) |
| T12.5 Inicio y navegador | Recientes, crear/abrir; árbol de capítulos con carga perezosa; estados de minuto (22.3) |
| T12.6 Diálogos y avisos | Cambios sin guardar, proyecto bloqueado, restaurar autosave, cascadas de renombres, conflictos de disco, errores (22.5) |
| T12.7 Teclado | `atajos.json` con **contextos de foco** (monitor, timeline, taller, campo de texto): en un campo de texto no se disparan atajos |
| T12.8 Tema | Tokens de color y tipografía en `app/ui/recursos/temas/oscuro.json` (22.3) |

**E13. Monitor y control espacial** — monitor con los 4 niveles, transporte con J K L, selector de idioma de escucha, mesa de trabajo, reglas, asas (dibujadas en `canvas` al instante), ancla, imán (bordes, centro, otros Elementos, guías), márgenes seguros, guía 9:16, zoom del lienzo.

**E14. Timeline y mapa del capítulo** — capas con alto ajustable, zoom por granularidad, dibujo solo de lo visible, arrastre con fusión de comandos, herramientas (selección, cuchilla, ripple, roll, slip, slide), imán a cortes, marcadores y cabezal, desbordes fantasma, pistas Global, cabecera de capa (ver, silenciar, bloquear, solo), selección múltiple, seguir al cabezal al cruzar de minuto, activar/desactivar imán, entrada y salida en la timeline, búsqueda de Elementos, ir a la Pieza de origen, idioma de cada capa A en su cabecera, mapa de 24 celdas con los dos estados.

**E15. Taller** — Brutos con fps y avisos; detección de escenas y de silencios; sincronía de audio externo; mini-timeline en fotogramas nativos; selector de `fps_interpretado` y método; tramos; horneado con progreso; ida y vuelta con el minuto.

**E16. Inspector, keyframes y curvas** — propiedades por grupo (espacio, audio, efectos, texto), rombo de keyframe por propiedad, navegación entre keyframes, editor de curvas bezier, panel de historial.

### Orden de lo que falta (revisión 10)

Criterio, de abajo hacia arriba como en todo el plan: **primero terminar la base
de edición diaria** (lo que la interfaz ya muestra pero no completa), después lo
creativo, luego la entrega y al final la extensión y el cierre. Cada fase solo
usa lo que ya existe debajo.

```
A Fundamentos → B Persistencia → C Motor → D Interfaz        (hecho, E0–E16)
  → E Completar la edición   E17 Timeline y Taller completos · E18 Proyecto, idiomas y mantenimiento
  → F Capacidades creativas  E19 Efectos, transiciones y texto · E20 Audio avanzado
  → G Entrega                E21 Render y exportación · E22 Shorts verticales 9:16
  → H Extensión y cierre     E23 Plugins y plantillas · E24 Rendimiento, empaquetado y documentación
```

### Fase E — Completar la edición

**E17. Timeline y Taller completos** — mover y recortar **en grupo** con la
selección múltiple (un solo paso de deshacer); miniaturas y forma de onda
dibujadas en las pistas (los servicios ya las generan al hornear); línea de
volumen editable en las pistas A (keyframes de `volumen`); transiciones
**visibles y editables** en la timeline con `DescriptorTransicion` (mismo patrón
que los efectos) sobre el comando `CambiarTransicion` ya existente; colocar audio
en A2+ y elegir la capa de audio destino; búsqueda de Elementos por nombre;
Taller: detección de escenas y de silencios (marcas sugeridas de entrada y
salida), sincronía de audio externo por forma de onda, ajuste por tramo cuando
los tramos de una Pieza tienen distinta relación de aspecto.

**E18. Proyecto, idiomas y mantenimiento** — comando para agregar, quitar y
ordenar los **idiomas del proyecto** (hoy solo al crearlo) y su pantalla;
descargar de memoria los capítulos sin historial al cambiar de capítulo; atajos
editables desde la interfaz; gestor de proyecto: consolidar, limpiar Brutos sin
uso, vaciar caché y papelera con confirmación; espacio en disco antes de
importar, hornear y renderizar (22.6).

### Fase F — Capacidades creativas

**E19. Efectos, transiciones y texto** — nuevos tipos de efecto con su
descriptor (máscaras, estabilización, Ken Burns, animaciones de entrada y salida
de clips); tipos de transición completos; curvas de los parámetros de efectos en
el editor de curvas; `DescriptorAnimacionTexto`, plantillas de títulos y rótulos;
títulos y subtítulos por idioma; importar `.srt`; velocidad y rampas (keyframes
de velocidad); monitores de señal (histograma, forma de onda de luminancia).

**E20. Audio avanzado** — reducción automática de la música con voz, medidores
de nivel, normalización de sonoridad (−14 LUFS para YouTube), reducción de
ruido, estiramiento de audio que **conserve el tono** (velocidad y conformar).

### Fase G — Entrega

**E21. Render y exportación** — lista de trabajos de render (hoy: barra de
tareas y entregables), perfiles en el estándar (YouTube 1080p, 720p, 4K, solo
audio), subtítulos `.srt` y en pista, capítulos de YouTube desde marcadores,
H.265 / 10 bits, NVENC; VAAPI con PyAV compilado contra el FFmpeg del sistema
(15.4).

**E22. Shorts verticales 9:16** — modelo y comandos ya listos (E4, E6); servicio
de recomposición a 720×1280; espacio de trabajo Shorts sobre `asas.VistaLienzo` y
`Lienzo.ventana_vertical`; `main.py --shorts`.

### Fase H — Extensión y cierre

**E23. Plugins y plantillas** — plugins desde `~/.config/editor/plugins/` (con
aviso: es código externo) que registran efectos, transiciones y exportadores con
sus descriptores; plantillas de capítulo; subtítulos automáticos opcionales.

**E24. Rendimiento, empaquetado y documentación** — capítulos grandes (cientos
de Elementos por minuto) en mapa y timeline; mediciones de memoria y tiempos;
empaquetado para Linux; README y este documento al día.

### Numeración anterior

Las revisiones 1–9 usan la numeración vieja de las épicas pendientes:

| Antes | Ahora |
|---|---|
| E15 (pendientes: escenas, silencios, sincronía) y seguimientos de E14 | E17 |
| E18 "gestión de idiomas del proyecto" y parte de E21 "gestor de proyecto, atajos editables" | E18 |
| E17 Efectos, transiciones y texto | E19 |
| E18 Audio avanzado | E20 |
| E19 Cola de render y exportación | E21 |
| E20 Shorts | E22 |
| E21 Extras (plugins, plantillas) | E23 |
| E22 Documentación final | E24 |

### Estado de implementación

| Épica | Estado | Notas |
|---|---|---|
| E0 | ✅ | qwen y deep eliminados; árbol `editor/` con módulos pendientes marcados con su épica; `main.py`, `requirements.txt`, `config/`, README |
| E1 | ✅ | `estandar`, `ajustes`, `eventos`, `utiles/` (registro, matemáticas, interpolación con curvas CSS y bezier) |
| E2 | ✅ | `granularidad` (Instante, Duración, minutos, fps de fuentes) y `nomenclatura` (Elementos, Shorts, Brutos, Piezas, capítulos, minutos, renders, IDs) |
| E3 | ✅ | `geometria` (Rect, imán), `transform` (Afin, Transform, recorte, compensación de ancla, ajuste inicial), `lienzo` (visibilidad, región de interés, márgenes, ventana vertical) |
| E4 | ✅ | Modelo completo (con idiomas por capa desde la revisión 5). La Pieza es por ahora una secuencia lineal de tramos; las capas dentro de una Pieza quedan para más adelante |
| Revisión 4 | ✅ | Correcciones A1–A10 aplicadas; marcadores y estado de capas; carga perezosa de capítulos |
| E5 | ✅ | `serializacion`, `gemelo`, `manifiestos`, `estructura`, `bloqueo`, `estado_disco` (nuevo: último estado conocido), `diario`, `escaner` (carga perezosa e `Informe`), `reconciliador` (fases A/B/C, papelera, conflictos, materialización simple), `guion`, `autosave`; `main.py --nuevo` y `--escanear` |
| E6 | ✅ | `comando` (contrato, `EdicionCapitulo` con deshacer por instantáneas, IDs reservados, fusión de gestos), `compuesto`, `historial` (marca de guardado, eventos), `operaciones` y `fabrica` (nuevos), y los comandos de T6.4–T6.10, capas y marcadores (`capas.py`), rangos (`colocacion.py`) y Taller (`taller.py`) |
| E7 | ✅ | `motor_base`, `decodificador` (búsqueda exacta, reapertura si el archivo cambia), `cache_fotogramas`, `compositor` (descarte, región de interés, transiciones, modos de mezcla, ventana para Shorts), `texto` (con animaciones), `efectos/` (registro ampliable: brillo, contraste, saturación, temperatura, desenfoque, nitidez, croma, LUT), `conversion_fps` (5 métodos), `codificador` (H.264, NVENC, ProRes 4444, AAC, WAV) |
| E8 | ✅ | `mezclador_audio`: 2000 muestras por fotograma, velocidad y reversa, rampas de volumen y paneo, cruces por transición, idiomas, limitador |
| E9 | ✅ | `tareas/cola` y servicios `fuentes`, `importacion` (fps medido y fps variable), `horneado` (+ `aplicar_horneado`), `banco` (+ `GestorFuentesBanco`), `miniaturas`, `forma_onda` |
| E10 | ✅ | `huellas` (video por minuto, audio por idioma), `render` (caché de minutos, modos `pistas` y `archivos`, `registrar`), `ensamblado` (sin recodificar, faststart); `main.py --render` y `--fotograma` |
| E11 | ✅ | `vista_previa` (niveles 1–4, audio por rango, pre-render por minuto, `RelojAudio`) y `guardado` (materialización pendiente, autosave) |
| E12 | ✅ | `aplicacion`, `estado` (Sesion), ventana con divisores y 5 espacios de trabajo, inicio, navegador, diálogos, teclado por foco, tema, autosave periódico, cierre seguro |
| E13 | ✅ | Monitor (niveles 2, 3 y 4 con reloj de audio y respaldo en vivo), asas, ancla, imán, márgenes seguros, guía 9:16, zoom, Alt + flechas |
| E14 | ✅ | Timeline (4 zooms, 6 herramientas, imán, fantasmas, Global, cabeceras de capa con idioma, marcadores, I/O, texto) y mapa del capítulo (3 estados, listo, intercambiar) |
| E15 | ✅ (parcial) | Brutos, visor nativo, fps interpretado, método, tramos, hornear, colocar. Pendiente: detección de escenas y silencios, sincronía de audio externo |
| E16 | ✅ | Inspector por grupos, keyframes (rombo, saltar), editor de curvas con bezier, historial |
| E17 | ✅ | Timeline y Taller completos (revisión 11) |
| E18 | ✅ | Proyecto, idiomas y mantenimiento; un capítulo en memoria |
| E19 | ✅ | Efectos, transiciones y texto; rampas; monitores de señal (revisión 12) |
| E20 | ✅ | Audio avanzado: ducking, medidores, −14 LUFS, reducción de ruido, conservar tono |
| E21 | **Siguiente** | Render y exportación |
| E22–E24 | Pendiente | |

### Decisiones tomadas al implementar la Fase B

| Tema | Decisión |
|---|---|
| Deshacer | Cada `EdicionCapitulo` guarda copias de los Elementos que toca y deshacer las restaura. La interfaz debe referirse a los Elementos por ID, no por objeto |
| Fusión de arrastres | Solo comandos con valores absolutos (mover, recortar, roll, slip, slide, transformar, cambiar propiedad o parámetro, poner keyframe); ventana de 1 s y nunca sobre el estado guardado |
| Quitar con ripple | Cierra el hueco **en la misma capa** |
| Ripple de recorte | Corre **todas las capas** de los minutos dentro del alcance (no Global), para conservar la sincronía |
| Modo insertar | Divide lo que cruza el punto en la capa del Elemento y corre todo lo posterior del alcance |
| Materialización | El reconciliador copia cuando la fuente tiene la misma extensión; extraer audio y convertir formatos quedan en `pendientes` para el servicio de guardado (E9) |
| Guardar sin cambios | 0 operaciones: solo se escribe lo que cambió (comparación por huella) |
| Bloqueo | También impide abrir dos veces el proyecto desde el mismo proceso |
| Verificación | Sin tests en el repositorio. Recorridos temporales fuera del repo: el primero (crear, editar, guardar, deshacer tras guardar, reabrir, intercambiar minutos, conflicto externo, bloqueo) corrigió 3 fallos; el de la revisión 6 (todos los comandos, 43 pasos de deshacer y rehacer) corrigió B1–B10 |

### Dependencias entre épicas

```
E0 → E1 → E2 → E3 → E4 ─┬→ E5 ─┐
                        ├→ E6 ─┼→ E9 → E10 → E11 → E12 → E13 → E14 → E15 → E16
                        └→ E7 → E8 ─┘                                        │
          ┌──────────────────────────────────────────────────────────────────┘
          └→ E17 → E18 → E19 → E20 → E21 → E22 → E23 → E24
```

E19 (efectos, transiciones) y E20 (audio) pueden avanzar en paralelo una vez
hecha E18; E22 (Shorts) usa el render de E21.

E5, E6 y E7 dependen solo de E4 y pueden avanzar en paralelo; E9 necesita las
tres (y E8).

---

## 20. Especificaciones aspirables

Metas, no garantías.

| Aspecto | Objetivo |
|---|---|
| Banco al hornear | Más rápido que el tiempo real |
| Scrubbing | < 50 ms |
| Vista previa en vivo | 256×144 a 640×360 · 10–15 fps · 3–4 capas de video · audio sincronizado (**medido: ~218 fps a 256×144** con 3 capas) |
| Vista previa fluida | 960×540 · 24 fps |
| Fotograma exacto en pausa | ~150–300 ms (**medido: ~130 ms a 1280×720**) |
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
| API de Flet cambiante | Versión fijada (`flet`, `flet-video`, `flet-audio` y `flet-desktop` en 1.0.2, siempre iguales); Flet aislado en `app/ui` |
| Latencia del reloj de audio (`get_current_position` asíncrono) | Extrapolar con `time.monotonic()` entre consultas (T11.3) |
| VAAPI ausente en PyAV binario | NVENC o software; compilar PyAV contra el FFmpeg del sistema si hace falta |
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

---

## 22. Contratos de integración núcleo ↔ pantallas

Lo que las pantallas (E12–E20) pueden esperar del núcleo, y lo que el núcleo
espera de ellas.

### 22.1 Estado de la aplicación (`EstadoApp`)

El modelo es el proyecto; `EstadoApp` es **cómo lo está mirando el usuario**.
No se deshace, no dispara huellas ni renders y no se guarda en el proyecto.

| Campo | Qué es | Persistencia |
|---|---|---|
| `proyecto` | Proyecto abierto (o ninguno) | Ruta en recientes (`~/.config/editor/`) |
| `solo_lectura` | Abierto con el bloqueo de otra instancia | — |
| `capitulo`, `minuto` | Dónde está el usuario | Último por proyecto, en `~/.config/editor/` |
| `cabezal` | Fotograma del capítulo | Igual |
| `seleccion` | IDs de Elementos (del capítulo actual) o de un Short | — |
| `idioma_escucha` | Idioma que suena en la vista previa (por defecto el principal) | — |
| `herramienta` | Selección, cuchilla, ripple, roll, slip, slide | — |
| `zoom_timeline`, `desplazamiento_timeline` | Nivel de granularidad y posición | — |
| `zoom_lienzo` | 25 %, 50 %, 100 %, encajar | — |
| `espacio_trabajo` | Taller, Minuto, Capítulo, Shorts, Render | `distribucion.json` |
| `reproduciendo`, `nivel_vista_previa` | Estado del transporte | — |
| `foco` | Monitor, timeline, taller, campo de texto | — |
| `portapapeles` | Copia serializada de Elementos | — |
| `tareas` | Tareas de fondo con su progreso | — |
| `avisos` | Mensajes pendientes | — |

Reglas:
- Si un Elemento seleccionado se quita (`ElementoQuitado`), sale de la selección.
- La selección se limita al capítulo actual; cambiar de capítulo la vacía.
- Al reproducir, si el cabezal cruza de minuto y "seguir cabezal" está activo, la timeline cambia de minuto sola.

### 22.2 Contrato de los comandos

```
Controlador (N5)                   Historial (N3)                 Bus (N0)
   │ crea MoverElemento(...)          │                              │
   │─── historial.ejecutar(cmd) ─────►│ cmd.validar() → error: nada cambia
   │                                  │ cmd.ejecutar(proyecto)       │
   │                                  │ apila / fusiona              │
   │                                  │─── ElementoCambiado(minutos_afectados) ──►
   │                                  │─── HistorialCambiado ───────────────────►
   │                                  │─── ProyectoModificado ──────────────────►
   │◄── resultado / ErrorModelo ──────│                              │
```

- La interfaz **nunca** modifica el modelo directamente.
- Un `ErrorModelo` (por ejemplo `Solapamiento`) vuelve al controlador y se muestra como aviso; el modelo queda intacto.
- Arrastres: un comando por gesto, fusionado mientras dura; al soltar queda un solo paso de deshacer.

### 22.3 Lenguaje visual

Tokens en `app/ui/recursos/temas/oscuro.json` (tema oscuro por defecto):

| Uso | Token | Criterio |
|---|---|---|
| Capas V / A / T | `capa_video`, `capa_audio`, `capa_texto` | Azul, verde y ámbar; Global con el mismo color y borde violeta |
| Selección | `seleccion` | Borde claro de 2 px |
| Desborde fantasma | `fantasma` | Contorno punteado, relleno al 30 % |
| Más allá de 24:00 | `fuera_marco` | Rayado atenuado |
| Fuera de línea | `error` | Rojo con rayado |
| Bloqueado | — | Candado y 60 % de opacidad |
| Capa oculta | — | 40 % de opacidad |

**Estados del minuto** en el mapa y el navegador (dos ejes a la vez):

| Eje | Cómo se ve | Valores |
|---|---|---|
| Trabajo | **Relleno** de la celda | vacío: gris oscuro · en progreso: ámbar · listo: azul |
| Render | **Punto** en la esquina | sin render: sin punto · desactualizado: rojo · al día: verde |
| Avisos | Icono | fuera de línea, conflicto de disco |

Cursores por herramienta; el cabezal y los marcadores con su color en todas las vistas.

### 22.4 Hilos y asincronía con Flet 1.0

- Los manejadores de la interfaz pueden ser `async`; los métodos de `Video` y `Audio` (`play`, `pause`, `seek`, `get_current_position`) **son asíncronos**.
- El núcleo es síncrono. Las operaciones largas van siempre a la cola de tareas (E9), nunca al manejador de un clic.
- Los eventos del bus pueden llegar desde hilos de trabajo; `app/estado.py` los pasa al bucle de Flet con `page.run_task` y **agrupa** los redibujados (como máximo uno por cuadro).
- El tic de la vista previa en vivo (nivel 2) es una tarea asíncrona de Flet que consulta el reloj de audio (T11.3). La composición del fotograma corre en `asyncio.to_thread` sobre una instantánea tomada en el bucle.
- Los manejadores **síncronos** de Flet 1.0 corren en el propio bucle: el modelo solo se toca desde ese hilo. `hacer_en_principal` ejecuta directamente si ya está en el bucle y, si no, usa `page.run_task`; sin conexión (ventana cerrada) descarta la llamada.
- Las llamadas a `Audio` y `Video` llevan tiempo máximo: si el sistema no tiene salida de sonido o libmpv, la reproducción sigue con el reloj monotónico y en vivo.

### 22.5 Secuencias principales

**Abrir un proyecto**
1. `main.py` → servicio de proyecto → `proyecto_fs`: bloqueo → diario pendiente → `_proyecto.json` → Taller → cargador de capítulos.
2. ¿Autosave más reciente? → diálogo restaurar.
3. `ProyectoAbierto` → navegador; se carga el último capítulo visitado.

**Importar → preparar → colocar**
1. Importar (tarea): copia a `brutos/`, análisis, `BrutoImportado`; aviso si el fps necesita revisión.
2. Taller: tramos, fps interpretado, método → comandos del Taller (`PiezaModificada`).
3. Hornear (tarea): archivo normalizado → `PiezaHorneada` → `actualizar_fuente` → banco (tarea) → `BancoListo`.
4. Arrastrar la Pieza a un minuto → `AgregarElemento`. La vista previa lee el horneado (T9.2) hasta que se guarde.

**Editar**: gesto → comando → eventos → timeline, inspector y monitor se redibujan → huella → `MinutoInvalidado` → pre-render en cola.

**Guardar**: servicio de guardado → reconciliador (plan) → diario → materialización → renombres en dos fases → gemelos y manifiestos → guion → `ProyectoGuardado` → marca de guardado en el historial.

**Deshacer después de guardar**: el historial vuelve atrás → modelo modificado → el siguiente guardado reconcilia (recuperando desde `.papelera/` si hace falta).

**Renderizar**: huellas → minutos desactualizados a la cola → render de minuto → audio en una pasada → ensamblado → `RenderTerminado` → registro y mapa en verde.

**Cerrar**: ¿cambios? → diálogo → detener tareas → completar diario → liberar bloqueo.

### 22.6 Errores y diálogos

| Situación | Comportamiento |
|---|---|
| Regla del modelo violada (solapamiento, bloqueo, fuente insuficiente) | Aviso breve; no cambia nada |
| Cambios sin guardar al cerrar o cambiar de proyecto | Guardar / descartar / cancelar |
| Proyecto bloqueado por otra instancia | Abrir en solo lectura / cancelar |
| Autosave más reciente que el disco | Restaurar / descartar |
| Ripple de capítulo o mover minuto | Confirmación con cuántos archivos se renombrarán |
| Conflicto de disco al guardar | Lista de archivos en conflicto; recargar o conservar la versión del programa |
| Medio fuera de línea | Marco rojo en vista previa; acción "rematerializar" si existe la Pieza |
| Espacio en disco insuficiente | Antes de importar, hornear o renderizar |
| Error en una tarea de fondo | `TareaTerminada(exito=False)`; aviso con el mensaje; la tarea se puede reintentar |

### 22.7 Estado del usuario y estado automático

| | Estado del usuario | Estado automático |
|---|---|---|
| Qué es | Lo que el usuario edita: Elementos, capas, marcadores, Shorts, recetas, títulos | Lo que producen los servicios: horneados, renders, entregables, análisis de Brutos, archivo materializado |
| Cómo cambia | Solo con comandos (se deshace) | Solo los servicios (no se deshace) |
| Cuándo se escribe | Al guardar (reconciliador) | En el momento (`proyecto_fs/automatico.py`) |
| Dónde | Gemelos, `_capitulo.json`, `_minuto.json`, `_pieza.json`, recetas de Shorts, `_proyecto.json` | `render/_renders.json`, `_horneado.json` |

Reglas: deshacer nunca revierte estado automático; los servicios nunca escriben
archivos del usuario.

### 22.8 Reglas de integración para la Fase C

| Regla | Motivo |
|---|---|
| Las tareas de fondo **nunca** llaman a `proyecto.capitulo()` ni modifican el modelo | La carga perezosa y los comandos solo corren en el hilo principal; los trabajadores reciben instantáneas: `Capitulo.instantanea(inicio, fin)` copia solo los Elementos del rango (el capítulo entero puede costar ~100 ms) |
| Un capítulo con pasos en el historial o sin guardar **no se descarga** | Los comandos lo necesitan para deshacer |
| La interfaz y los servicios se refieren a los Elementos **por ID** | Deshacer restaura copias, no los mismos objetos |
| `Elemento.archivo` puede estar vacío o desactualizado | Es estado automático; el motor resuelve siempre con `servicios/fuentes.py` (T9.2) y comprueba que exista |
| Horneado → `automatico.guardar_horneado` → `actualizar_fuente(pieza, asas_anteriores, capítulos)` → `PiezaHorneada` | Los capítulos salen de las copias de `_pieza.json` (`EstadoDisco.copias_piezas`) |
| Render → `automatico.guardar_renders` → `RenderTerminado` | El registro no depende de que el usuario guarde |
| Las `Materializacion` pendientes del guardado las resuelve el servicio de guardado | Extraer audio y convertir formatos necesitan el motor |

API del núcleo que usa la Fase C:

| Necesidad | Llamada |
|---|---|
| Qué se ve en f | `Capitulo.visuales_activos_en(f)` (ya ordenado de abajo hacia arriba, respeta capas ocultas) |
| Qué suena en f | `Capitulo.sonoros_activos_en(f, idioma)` (respeta silencio, solo e idioma) |
| Transiciones en curso | `Capitulo.transiciones_activas(f)` |
| Fotograma de la fuente | `Elemento.fotograma_fuente(f)` (velocidad, reversa y congelado incluidos) |
| Transformación y matriz | `Elemento.transform_en(f).matriz_a_resolucion(factor)` |
| Visibilidad y región | `Lienzo.visibilidad(...)`, `Lienzo.region_interes(..., factor)` |
| Volumen y paneo | `Elemento.volumen_en(f)`, `Elemento.paneo_en(f)` |
| Efectos | `Efecto.valores_en(f_local)` |
| Ventana de un Short | `Short.rect_en(f)` |
| Lo que afecta a un minuto | `Capitulo.que_afecta_al_minuto(n)` + `serializacion.huella(...)` |
| Resultado del guardado | `ResultadoGuardado.pendientes` / `.errores` / `.conflictos` |

### 22.9 Cómo usa la interfaz (Fase D) la Fase C

| Necesidad de la pantalla | Llamada | Dónde corre |
|---|---|---|
| Imagen del monitor al mover el cabezal o editar | `ServicioVistaPrevia.fotograma_rapido(copia_capitulo, f, tamaño)` → bytes JPEG | Tarea prioridad 1 con `clave="monitor"` (la nueva reemplaza a la vieja) |
| Imagen en pausa | `fotograma_exacto(...)` | Tarea prioridad 1, `clave="monitor"` |
| Reproducción fluida | `prerender_minuto(...)` → `.mp4` para `flet_video.Video` | Tarea prioridad 3 (minuto actual) o 5 (resto), `clave` por minuto |
| Audio del transporte | `audio(capitulo, inicio, fin, idioma)` → `.wav` para `flet_audio.Audio` + `RelojAudio` | Tarea prioridad 3 |
| Tras importar | `importacion.preparar_bruto` (principal) → `copiar_y_analizar` (tarea) → `AgregarBruto` + `BrutoImportado` (principal) | — |
| Tras hornear | `horneado.hornear` (tarea) → `aplicar_horneado` (principal) → `banco.generar`, `miniaturas`, `forma_onda` (tareas) → `ServicioVistaPrevia.actualizar_taller` | — |
| Guardar | `ServicioGuardado.guardar()`; `en_hilo_principal` = `hacer_en_principal(page)` (usa `page.run_task`) | Principal |
| Renderizar | `render.PedidoRender.crear` (principal) → `renderizar` (tarea prioridad 6) → `render.registrar` (principal) | — |
| Minutos listos para reproducir | `minutos_listos(capitulo, idioma)` → barra verde/roja del mapa | Principal (solo comprueba archivos) |

Regla: todo `al_terminar` de una tarea llega en un hilo de trabajo; la app lo
pasa al hilo de Flet antes de tocar el modelo o la interfaz.

---

## 23. Casos de uso futuros contemplados

No están en las épicas actuales, pero la arquitectura ya deja el hueco:

| Caso | Hueco previsto |
|---|---|
| Capas dentro de una Pieza | `Pieza` puede pasar a contener una `Composicion` sin cambiar el Elemento |
| Interfaz PySide6 | `core/` no depende de Flet |
| Motor MLT u otro | `motor_base` |
| VAAPI | Parámetro `aceleracion` del estándar + PyAV compilado |
| Importar y exportar subtítulos `.srt` | Elementos T con tiempo y texto |
| Exportar EDL / XML para otros editores | Nombres y gemelos ya contienen el tiempo exacto |
| Plantillas de proyecto o de capítulo | Estructura y manifiestos reutilizables |
| Varias pistas de idioma de audio | Capas A de Global |
| Migrar proyectos a un formato nuevo | `version_esquema` |
| Trabajo entre varios equipos | Bloqueo, diario y papelera |

---

## 24. Funciones tomadas de editores equivalentes

Referentes: Adobe Premiere Pro, DaVinci Resolve, Final Cut Pro, CapCut, Kdenlive y
Shotcut. Se eligieron las que mejoran el flujo por capítulos y minutos, la
calidad de entrega o la velocidad de edición.

### 24.1 Edición

| Función | Referente | Qué aporta | Épica |
|---|---|---|---|
| **Modos insertar / sobrescribir** al colocar un Elemento | Premiere, Resolve, FCP | Hoy un solape se rechaza; con estos modos, insertar empuja lo siguiente (ripple) y sobrescribir recorta lo que tapa | E6 |
| **Edición de tres puntos** (entrada y salida en fuente y timeline) | Premiere, Resolve | Colocar tramos exactos sin arrastrar | E6, E14 |
| **Levantar / extraer** un rango marcado | Premiere | Quitar un rango dejando hueco o cerrándolo | E6 |
| **Cerrar huecos** del minuto | Resolve, CapCut | Un paso para compactar | E6 |
| **Congelar fotograma** | Premiere, CapCut | Elemento de imagen a partir de un fotograma | E6 |
| **Reproducción J K L** (atrás, pausa, adelante, más rápido con repeticiones) | Todos | Navegación estándar profesional | E13 |
| **Activar / desactivar imán** (tecla) | Todos | Control fino | E14 |
| **Buscar Elementos** por nombre en capítulo y proyecto | Premiere, Resolve | Imprescindible con 1000 capítulos | E14 |
| **Ir a la Pieza de origen** (match frame) | Premiere, FCP | Del minuto al Taller en el fotograma exacto | E14 |
| **Panel de historial** | Premiere, Photoshop | Ver y saltar a cualquier paso de deshacer | E16 |

### 24.2 Taller y medios

| Función | Referente | Qué aporta | Épica |
|---|---|---|---|
| **Detección de escenas** al importar | Resolve, PySceneDetect | Divide un Bruto largo en tomas sugeridas | E15 |
| **Detección de silencios** (cortes automáticos en voz) | CapCut, Descript | Acelera videos hablados | E15 |
| **Sincronizar audio externo por forma de onda** | Premiere, Resolve | Micrófono separado alineado solo | E15 |
| **Estabilización** | Resolve, Premiere | Horneada en la Pieza (OpenCV) | E17 |
| **Revincular medios** | Todos | Brutos movidos o renombrados fuera del programa | E9 |

### 24.3 Imagen

| Función | Referente | Qué aporta | Épica |
|---|---|---|---|
| **Máscaras** (rectángulo, elipse, con difuminado, animables) | Premiere, Resolve | Recortes no rectangulares, desenfocar caras o logos | E17 |
| **Animaciones de entrada y salida de clips** (no solo de texto) | CapCut | Zoom, deslizamiento, rebote en un clic | E17 |
| **Efecto Ken Burns** automático en imágenes | FCP, iMovie | Fotos con movimiento | E17 |
| **Plantillas de títulos y rótulos** (lower thirds) | Premiere, CapCut | Rótulos consistentes en todos los capítulos | E17 |
| **Monitores de señal** (histograma, forma de onda, vectorscopio) | Resolve | Control de calidad de color por minuto | E17 |

### 24.4 Audio

| Función | Referente | Qué aporta | Épica |
|---|---|---|---|
| **Normalización de sonoridad (LUFS)** — −14 LUFS para YouTube | Resolve (Fairlight), Premiere | Volumen correcto y parejo entre capítulos; medición ITU-R BS.1770 con numpy | E18 |
| **Reducción automática de la música con voz** (ducking) | Premiere, CapCut | Ya prevista | E18 |
| **Reducción de ruido** básica | Resolve, Audacity | Voz más limpia | E18 |
| **Pistas de idioma** y exportación por idioma | Resolve, plataformas de streaming | Doblaje y subtítulos | E8, E10, E18 (13.6) |

### 24.5 Entrega y gestión

| Función | Referente | Qué aporta | Épica |
|---|---|---|---|
| **Perfiles de exportación** (YouTube 1080p, 720p, 4K; solo audio) | Todos | Un clic por destino | E19 |
| **Capítulos de YouTube** desde los marcadores (`00:00 Intro`…) | Resolve | Texto listo para la descripción del video | E19 |
| **Subtítulos `.srt`** por idioma, importar y exportar | Todos | Accesibilidad y traducción | E17, E19 |
| **Gestor de proyecto**: consolidar, quitar Brutos sin usar, vaciar caché y papelera | Premiere (Project Manager) | Controla el disco con la materialización | E21 |
| **Plantilla de capítulo** (intro, cierre y Global comunes) | FCP, CapCut | Empezar cada capítulo con su estructura | E21 |

Quedan fuera por ahora (se pueden sumar después): edición multicámara, seguimiento de
movimiento (tracking) y subtítulos automáticos por reconocimiento de voz (ya
previstos en E21 como opcionales, por lo pesado de sus dependencias).
