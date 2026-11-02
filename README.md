# ¿Tener red pública garantiza agua segura en el Perú?

**Tarea 3 – Python Intermedio** · Del dato a la historia: dashboard interactivo y reel con IA

## 1. Tema y pregunta de investigación

**Tema:** acceso a agua segura en el Perú (ODS 6, meta 6.1).

**Pregunta:** ¿Qué criterio de agua segura (acceso a red pública, continuidad del servicio o cloración) limita el cumplimiento del indicador ODS 6.1.1 en el Perú, y cómo cambió entre 2019 y 2025 en las áreas urbanas y rurales y en los departamentos?

- **Cobertura geográfica:** nacional, urbano/rural y 25 departamentos (24 + Callao).
- **Cobertura temporal:** 2019 (prepandemia) vs 2025 (último año publicado de la ENAPRES), con 2022, 2023 y 2024 para la evolución. 2020 y 2021 se excluyen (ver Limitaciones).

## 2. Descripción del proyecto

El indicador ODS 6.1.1 considera que una persona tiene agua "gestionada de forma segura" si su fuente está en la vivienda, disponible cuando se necesita y libre de contaminación. El Ministerio de Vivienda (MVCS) lo calcula para el Perú con la ENAPRES como el menor de tres indicadores: acceso, continuidad de 24 horas y calidad del agua. Este proyecto reconstruye ese indicador desde los microdatos, lo desagrega por departamento e identifica el criterio que actúa como cuello de botella en cada territorio.

## 3. Fuentes de datos y metodología

### Fuentes

| Fuente | Uso | Acceso |
|---|---|---|
| INEI – Encuesta Nacional de Programas Presupuestales (ENAPRES) 2019 y 2022–2025, capítulos 100 (vivienda y hogar) y 200 (residentes) | Datos principales | Portal de microdatos del INEI. Códigos de descarga en `config/anios/`; fechas y URL en `datos/originales/registro_descargas.csv` |
| MVCS – serie del ODS 6.1.1 (2018–2023) y Plan Nacional de Saneamiento 2022–2026 | Validación (réplica) | `references/fuentes.md` |
| INEI – *Acceso a los servicios básicos en el Perú* (ediciones 2013–2019, 2021, 2024, 2025 y año móvil jul 2025–jun 2026) | Validación en hogares, nacional y departamental (réplica) | `references/fuentes.md` |
| INEI – boletín *Formas de acceso al agua y saneamiento básico* | Validación del cloro rural (réplica) | `references/fuentes.md` |
| JMP OMS/UNICEF | Contraste internacional | washdata.org / API del Banco Mundial |
| MVCS/MEF – fichas técnicas de indicadores de brecha (Formato 04-A) | Definición de las variables | `references/fuentes.md` |

### Construcción de los indicadores

Se sigue la **metodología del MVCS** (fichas técnicas y Plan Nacional de Saneamiento), con el capítulo 100 de la ENAPRES:

| Criterio ODS 6.1.1 (MVCS) | Variable | Definición |
|---|---|---|
| Acceso | P129G | Red pública: códigos 1, 2 o 3 (dentro de la vivienda, fuera de la vivienda pero dentro de la edificación, pilón de uso público) |
| Continuidad | P130, P130A | Agua todos los días (P130 = 1) y 24 horas (P130A = 24) |
| Calidad (proxy) | P129D | Cloro residual libre ≥ 0,5 mg/L en la muestra del hogar |
| Red dentro de la vivienda (descriptivo, no entra en el 6.1.1) | P129G | Código 1 |

Los números de pregunta cambian entre años (verificado con el cuestionario urbano y rural y el diccionario de cada año):

| Criterio | 2019 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| Fuente de agua | P129A | P129G | P129G | P135 | P135 |
| Agua todos los días | P130 | P130 | P130Z | P138 | P138 |
| Horas al día | P130A | P130A | P130ZA | P138_A | P138_A |
| Cloro residual libre (mg/L) | P129D_ENT + P129D_DEC/10 | ídem | ídem | P166_ENT + P166_DEC/10 | ídem |

- **Código 9 "Red pública casa del vecino" (2024 y 2025): no se cuenta como red pública.** Se mantiene la definición de las fichas MVCS (códigos 1, 2 y 3) y la comparabilidad con 2019–2023, años en que esos hogares probablemente se registraban en "Otro" (esa categoría bajó de ~1.600–1.780 hogares a 723 en 2024, cuando apareció el código 9). Además, el cuestionario no les aplica la pregunta de continuidad (P138 solo se hace a los códigos 1–3).
- En 2019 la fuente de agua usa los códigos 6A (manantial) y 6B (río); se lee como texto para no excluir esos hogares.
- El cloro se registra como parte entera y décimas de la lectura del comparador. En 2019 y 2022, únicos años con la categoría oficial P129C, la reconstrucción coincide al 100% con esa categoría.

- **Agregación (MVCS):** el 6.1.1 es el menor de los tres indicadores (acceso a red pública, continuidad 24 h y calidad), calculado por separado en urbano y rural; el total es su promedio ponderado por población. A diferencia del JMP, el acceso no exige que la fuente esté dentro de la vivienda. Se reporta además el indicador **conjunto** (hogares que cumplen los tres a la vez).
- **Población (capítulo 200):** el dato de cada hogar se traslada a sus residentes habituales del capítulo 200 —miembros no ausentes 6 meses o más (P204 = 1 y P205 = 2) y no miembros presentes 6 meses o más (P204 = 2 y P206 = 1)— con el factor de expansión anual. Es el método oficial y da una población expandida de 32,4 millones (2019) a 34,2 millones (2025). El 6.1.1 se expresa en % de población; las réplicas del INEI usan además indicadores en % de hogares (factor del hogar).
- **Precisión:** error estándar por linealización de Taylor, con departamento × área como estrato y el conglomerado como unidad primaria de muestreo (ver Limitaciones). Estimaciones con CV > 15% se marcan como referenciales (criterio MVCS/INEI).
- **Comparación 2019 vs 2025 (y 2023 vs 2025):** diferencia en puntos porcentuales y prueba de significancia al 95%, tratando los años como muestras independientes. La distancia entre continuidad y cloro dentro de un mismo año se estima como diferencia en la misma muestra, de modo que su error estándar incluye la covarianza.
- **Población sin agua segura:** (100 − 6.1.1) % × población expandida. Como la población está calibrada a las proyecciones del INEI, se trata como fija: el error estándar es población × error estándar del 6.1.1.
- **Descomposición departamental:** el cambio del 6.1.1 nacional se reparte entre departamentos en un efecto tasa (peso poblacional medio × cambio de la tasa) y un efecto composición (tasa media × cambio del peso). Como el cloro es el criterio limitante en urbano y en rural en 2019 y 2025, el 6.1.1 nacional es igual al cloro adecuado nacional, y **la descomposición usa la tasa de cloro adecuado de cada departamento** (no su 6.1.1, que puede tener otro criterio limitante). El script comprueba esa condición antes de calcularla.
- **Sensibilidad:** continuidad con umbrales de 24 h (principal), 20 h y 12 h.

### Limpieza

Fuente: `datos/procesados/reporte_limpieza.csv`.

| | 2019 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| Hogares iniciales (capítulo 100) | 42.372 | 41.674 | 42.000 | 41.626 | 40.810 |
| Pares de hogares con llaves duplicadas | 0 | 7 | 0 | 7 | 7 |
| Hogares excluidos por duplicado (ambos registros) | 0 | 14 | 0 | 14 | 14 |
| Hogares sin fuente de agua | 0 | 0 | 0 | 0 | 0 |
| Horas de servicio inválidas (fuera de 0–24) | 0 | 0 | 0 | 0 | 0 |
| Lecturas de cloro inválidas (fuera de 0–3,5 mg/L) | 0 | 0 | 0 | 0 | 0 |
| Hogares sin área o departamento | 0 | 0 | 0 | 0 | 0 |
| Hogares con código 9 "red casa del vecino" (no cuentan como red) | – | – | – | 1.036 | 1.068 |
| Hogares con red pública sin prueba de cloro | 341 | 604 | 473 | 589 | 697 |
| Personas en el capítulo 200 | 150.620 | 147.489 | 147.007 | 143.002 | 137.639 |
| Residentes habituales | 144.788 | 141.045 | 140.761 | 136.971 | 132.394 |
| Registros finales (personas) | 144.788 | 140.994 | 140.761 | 136.922 | 132.354 |
| **Población expandida** | **32.418.579** | **33.315.057** | **33.685.925** | **34.017.437** | **34.201.633** |

- Las llaves del hogar son CONGLOMERADO, NSELV, VIVIENDA y HOGAR. Los pares duplicados tienen respuestas o factores distintos, por lo que no se puede saber cuál es el correcto: se excluyen ambos registros. Sus llaves están en la columna `duplicados_llaves`.
- No se filtran las entrevistas incompletas (RESFIN = 2): esos hogares sí respondieron agua y cloro, tienen factor de expansión mayor que cero y los factores están calibrados sobre todos los hogares.
- Los hogares con red y sin prueba de cloro cuentan como "sin cloro adecuado" en el 6.1.1, cuyo denominador es toda la población, igual que en el cálculo del MVCS.

### Validación

Fuente: `datos/procesados/validacion.csv` (cifras oficiales en `references/valores_referencia.csv`). Las 35 réplicas salen **OK** y ninguna sale REVISAR.

| Réplica | Años | Medida | Oficial | Propio | Mayor diferencia |
|---|---|---|---|---|---|
| MVCS – ODS 6.1.1 nacional | 2019, 2022, 2023 | % de personas | 41,5 · 36,5 · 34,5 | 41,5 · 36,5 · 34,5 | 0,0 pp |
| MVCS – ODS 6.1.1 urbano y rural | 2023 | % de personas | 42,1 · 3,0 | 42,1 · 3,0 | 0,0 pp |
| INEI – red pública y cloro adecuado, nacional, urbano y rural (12 cifras) | 2024, 2025 | % de hogares | p. ej. 2025 nacional: 90,7 y 38,4 | 90,7 y 38,4 | 0,1 pp (red pública rural 2024: 79,3 vs 79,4)¹ |
| INEI – cloro adecuado de Arequipa, el Callao y Tacna (15 cifras) | 2019, 2022–2025 | % de hogares | p. ej. Arequipa 2019 y 2025: 68,2 y 44,9 | 68,2 y 44,9 | 0,0 pp |
| INEI, boletín de agua – cloro en la red, rural | 2023 | % de personas con red y prueba | 4,0 · 7,2 · 88,8 | 3,8 · 7,8 · 88,4 | 0,6 pp (tolerancia: 1 pp)² |

¹ La diferencia exacta es 0,05 pp; se ve como 0,1 por el redondeo.
² El boletín usa años móviles, no año calendario.

Contrastes (otra definición o período; no se exige coincidencia):
- **MVCS, cloro urbano 2023 (43,3%):** es una cifra en **hogares** con prueba de cloro, de cualquier fuente; con esa definición el cálculo propio también da 43,3. El cloro que entra en el 6.1.1 (personas con red y cloro adecuado sobre toda la población) da 42,1.
- **INEI, años móviles jul 2024–jun 2025 y jul 2025–jun 2026:** % de hogares en otro período; no son comparables directamente con el año calendario.
- **JMP 2024 (49% total, 23% rural):** mide la calidad con E. coli y la disponibilidad "cuando se necesita", por eso queda muy por encima de la cifra con cloro.

## 4. Hallazgos principales

Cifras de `datos/procesados/` (también en `datos/procesados/tablas_revision.xlsx`). Porcentajes de población; "significativo" quiere decir al 95%.

### 1. El Perú retrocedió en agua segura: 2,7 millones de personas más sin ella

El indicador ODS 6.1.1 cayó de 41,5% en 2019 a 36,6% en 2025 (−5,0 pp, significativo al 95%). Las personas sin agua gestionada de forma segura pasaron de 19,0 a 21,7 millones. El punto más bajo fue 2023 (34,5%); la recuperación posterior (+2,1 pp, significativa) no alcanza el nivel prepandemia. El cálculo reproduce las cifras oficiales del MVCS (2019, 2022 y 2023) y del INEI (2024 y 2025).

*Confiabilidad:* CV del 6.1.1 nacional de 1,5% (2019) y 1,8% (2025). La recuperación 2023–2025 es significativa por poco (error estándar de 0,96 pp) y no lo es si se mira solo el área urbana.

### 2. El cloro es el cuello de botella, en la ciudad y en el campo

El cloro es el criterio limitante en las zonas urbanas y rurales en ambos años. En las ciudades, la caída de 7,5 pp del indicador se explica íntegramente por el cloro (51,8% → 44,3%), mientras la continuidad no cambió de forma significativa. En el campo hay una paradoja: entre 2019 y 2025 aumentaron la cobertura de red (+4,8 pp) y la continuidad (+4,2 pp), pero el agua con cloro adecuado sigue en torno al 3%. Así, 6,2 de los 6,4 millones de habitantes rurales no tienen agua segura.

*Confiabilidad:* el cloro urbano tiene CV de 1,5–1,8%. El cloro rural (3,6% → 3,1%) tiene CV de 13–14%, cerca del límite de 15%, y su cambio no es significativo.

### 3. Las caídas vinieron del cloro y las mejoras, de la continuidad

En 2025 el indicador va de 73,1% en el Callao a 14,1% en Huancavelica (entre departamentos con estimaciones confiables). La caída nacional fue amplia (19 de 25 departamentos bajaron), pero cinco departamentos explican cerca de dos tercios: Arequipa, Lima, Piura, La Libertad y Lambayeque. Arequipa sola, con el 4% de la población, explica una quinta parte: su cloro cayó de 69,7% a 44,5% mientras su continuidad se mantuvo estable. Los únicos avances significativos, en el Callao (+20,4 pp) y Tacna (+22,9 pp), vinieron de la mejora de la continuidad, no del cloro.

*Confiabilidad:* CV de 3,7% (Callao) y 12,7% (Huancavelica) en 2025; 12 de los 25 departamentos tienen CV > 15% en algún año y se tratan como referenciales. El cloro de Arequipa, el Callao y Tacna coincide con las cifras departamentales del INEI en todos los años. Para Tacna, ver Limitaciones.

## 5. Limitaciones

- **Calidad medida con cloro:** el cloro residual indica desinfección, no ausencia de contaminación fecal (el JMP usa pruebas de E. coli). La muestra se toma del caño o del recipiente donde el hogar almacena el agua, y solo existe si el hogar aceptó la prueba.
- **Red pública rural:** la ENAPRES cuenta como red pública los sistemas de organizaciones comunales aunque el agua no sea tratada.
- **Continuidad declarada** por el informante, no medida.
- **2020 y 2021 excluidos:** por la pandemia, el INEI redujo el cuestionario y aplicó entrevistas telefónicas, sin poder medir el cloro en el hogar; el MVCS usó factores de expansión calibrados para esos años.
- **Precisión:** la ENAPRES tiene inferencia nacional y departamental por área; las cifras con CV > 15% son referenciales.
- **Diferencias con el JMP:** distintas definiciones de acceso (red pública vs. fuente en la vivienda), de calidad (cloro vs. E. coli) y de disponibilidad (24 h vs. "cuando se necesita"), por lo que las cifras no son directamente comparables.
- **Urbano/rural:** según el umbral de 2000 habitantes del centro poblado.
- **Estrato de diseño aproximado:** los microdatos publicados no incluyen la variable de estrato del diseño muestral (la variable ESTRATO es el estrato socioeconómico A–E y está vacía en el área rural). Se usa departamento × área como pseudo-estrato y CONGLOMERADO como unidad primaria. Los errores estándar, los CV y las pruebas de significancia son una aproximación y podrían diferir algo de los del INEI.
- **Código 9 "red pública casa del vecino" (2024 y 2025):** no se cuenta como red pública, por comparabilidad con 2019–2023 y con las fichas MVCS. En 2025 corresponde al 2,7% de la población urbana. Como control de robustez, contarlo como red (con su lectura de cloro) sube el cloro adecuado y el 6.1.1 urbanos de 2025 de 44,3% a 45,2% (+0,9 pp); el cloro sigue siendo el criterio limitante y los hallazgos no cambian (`datos/procesados/robustez_codigo9_2025.csv`).
- **Cobertura urbana de red pública:** baja de 94,9% (2019) a 92,7% (2025). No se presenta como hallazgo porque depende de cómo se clasifique el código 9: contándolo, la cobertura urbana de 2025 sería 95,4%. La baja ya aparecía en 2022 (92,8%), antes de que existiera ese código.
- **Tacna:** la mejora del 6.1.1 (+22,9 pp) viene de la continuidad 24 h urbana (30,2% → 54,8%), que es declarada y tiene una serie irregular (30, 48, 39, 45 y 55% en 2019, 2022, 2023, 2024 y 2025; error estándar de 4–6 pp por año). Su magnitud depende de un 2019 bajo. El INEI no publica la continuidad de 24 h por departamento, así que esta cifra no se pudo contrastar; el cloro de Tacna sí coincide con el INEI y no cambió.
- **Población rural sin agua segura:** baja en 0,47 millones entre 2019 y 2025, sobre todo porque la población rural expandida se redujo (6,9 → 6,4 millones), no porque mejorara el indicador.

## 6. Enlaces

- Dashboard: <https://estefmej.github.io/Tarea_3/web/> (también abre desde <https://estefmej.github.io/Tarea_3/>, que redirige a `web/`)
- Reel (Google Drive): <https://drive.google.com/file/d/1ivPMWhHdh0Z4U1zqrKlihEIdyMfynvKO/view?usp=drive_link>

**Recursos del reel** (no se suben al repositorio; se usan bajo la licencia de contenido de Pixabay):

- Música: «Science Documentary», Lexin_Music (Aleksey Chistilin) · Pixabay Music: <https://pixabay.com/music/build-up-scenes-science-documentary-169621/>
- Foto de la escena 1: JonasKIM · Pixabay: <https://pixabay.com/photos/faucet-sink-tap-tap-water-flow-3240211/>

## 7. Cómo reproducir el proyecto

```bash
pip install -r requirements.txt

# 0) (opcional) Probar el flujo con datos falsos
python scripts/generar_prueba.py
python scripts/procesar_datos.py --config-dir datos/prueba/config
python scripts/analizar_datos.py --base 2019
rm -r datos/procesados/*        # limpiar antes de usar los datos reales

# 1) Obtener datos (códigos del INEI ya anotados en config/anios/<año>.json)
python scripts/obtener_datos.py --anios 2019 2022 2023 2024 2025 --dry-run
python scripts/obtener_datos.py --anios 2019 2022 2023 2024 2025

# 2) Limpiar y construir variables (verificar antes los nombres en config/)
python scripts/procesar_datos.py

# 3) Indicadores, comparación, validación y datos para la web
python scripts/analizar_datos.py --base 2019

# 4) Tablas de revisión en Excel (datos/procesados/tablas_revision.xlsx)
python scripts/exportar_tablas.py --base 2019 --final 2025
```

Los microdatos no se suben al repositorio por su tamaño; se descargan con el paso 1.

### Cómo generar el reel

El reel sigue el flujo de la Sesión 15 del curso (guion → voz clonada con Qwen3-TTS → subtítulos con Whisper → video con Pillow y ffmpeg) y va en un entorno propio, `reel/.venv`, con las versiones de `reel/requirements.txt`. La primera corrida descarga los modelos (Qwen3-TTS 1.7B, Whisper large-v3-turbo y WavLM para medir la similitud de voz).

```bash
cd reel
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python -r requirements.txt
.venv/Scripts/python -m playwright install chromium

# Insumos que no están en el repositorio: mi_voz.m4a (grabación de la autora),
# recursos/musica.mp3 y recursos/foto_escena1.jpg (Pixabay; enlaces en la sección 6)

# 1) Narración por escena con la voz clonada; regenera con otra semilla las escenas que se alejan del timbre
.venv/Scripts/python voces.py --tts Qwen/Qwen3-TTS-12Hz-1.7B-Base --margen 0.03
# (opcional) más versiones de algunas escenas y elección de la mejor
.venv/Scripts/python regenerar.py --tts Qwen/Qwen3-TTS-12Hz-1.7B-Base --buenas 2 3 --escenas 7 --semillas 101 202 --carpeta salidas/pruebas
.venv/Scripts/python regenerar.py --carpeta salidas/pruebas --elegir 7:101

# 2) Capturas del dashboard publicado (vista de celular a 3x, con los resaltados de cada escena)
.venv/Scripts/python capturar.py

# 3) Subtítulos, mezcla con la música (-14 dB respecto de la voz) y video 1080x1920
.venv/Scripts/python hacer_reel.py
```

El guion con las cifras y su fuente en `datos/procesados/` está en `reel/guion.json`; el resultado queda en `reel/reel.mp4` y `reel/subtitulos.srt`. Los audios intermedios se guardan en `reel/salidas/`, que no se sube. En la narración, la voz lee «Cayao» para pronunciar bien «Callao»; los subtítulos lo escriben correctamente.

## 8. Uso de inteligencia artificial

[Ajustar a lo que realmente hiciste.] Se usó Claude (claude.ai y Claude Code) para buscar fuentes y fichas metodológicas, escribir y depurar los scripts de procesamiento y análisis, y diseñar el dashboard. Las variables, cifras e interpretaciones fueron verificadas contra el diccionario de la ENAPRES y contra las publicaciones oficiales del MVCS y del INEI.
