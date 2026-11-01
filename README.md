# ¿Tener red pública garantiza agua segura en el Perú?

**Tarea 3 – Python Intermedio** · Del dato a la historia: dashboard interactivo y reel con IA

## 1. Tema y pregunta de investigación

**Tema:** acceso a agua segura en el Perú (ODS 6, meta 6.1).

**Pregunta:** ¿Qué criterio de agua segura (acceso en la vivienda, continuidad del servicio o cloración) limita el cumplimiento del indicador ODS 6.1.1 en el Perú, y cómo cambió entre 2019 y [AÑO FINAL] en las áreas urbanas y rurales y en los departamentos?

- **Cobertura geográfica:** nacional, urbano/rural y 25 departamentos (24 + Callao).
- **Cobertura temporal:** 2019 (prepandemia) vs [AÑO FINAL], con los años intermedios 2022–[AÑO] para la evolución. 2020 y 2021 se excluyen (ver Limitaciones).

## 2. Descripción del proyecto

El indicador ODS 6.1.1 considera que una persona tiene agua "gestionada de forma segura" si su fuente está en la vivienda, disponible cuando se necesita y libre de contaminación. El Ministerio de Vivienda (MVCS) lo calcula para el Perú con la ENAPRES como el menor de tres indicadores: acceso, continuidad de 24 horas y calidad del agua. Este proyecto reconstruye ese indicador desde los microdatos, lo desagrega por departamento e identifica el criterio que actúa como cuello de botella en cada territorio.

## 3. Fuentes de datos y metodología

### Fuentes

| Fuente | Uso | Acceso |
|---|---|---|
| INEI – Encuesta Nacional de Programas Presupuestales (ENAPRES), capítulo 100 | Datos principales | Portal de microdatos del INEI. Fechas y URL en `datos/originales/registro_descargas.csv` |
| MVCS – serie del ODS 6.1.1 (2018–2023) y Plan Nacional de Saneamiento 2022–2026 | Validación (réplica) | `references/fuentes.md` |
| INEI – boletín *Formas de acceso al agua y saneamiento básico* | Validación de cloro (réplica) | `references/fuentes.md` |
| JMP OMS/UNICEF | Contraste internacional | washdata.org / API del Banco Mundial |
| MVCS/MEF – fichas técnicas de indicadores de brecha (Formato 04-A) | Definición de las variables | `references/fuentes.md` |

### Construcción de los indicadores

Definiciones de las fichas técnicas del MVCS (capítulo 100 de la ENAPRES):

| Criterio ODS 6.1.1 | Variable | Definición |
|---|---|---|
| Accesible en la vivienda | P129G | Red pública dentro de la vivienda (código 1) |
| Disponible cuando se necesita | P130, P130A | Agua todos los días (P130 = 1) y 24 horas (P130A = 24) |
| Libre de contaminación (proxy) | P129D | Cloro residual libre ≥ 0,5 mg/L en la muestra del hogar |
| Red pública (cobertura) | P129G | Códigos 1, 2 o 3 (dentro, fuera de la vivienda en la edificación, pilón) |

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

- **Agregación (método JMP):** el indicador es el mínimo de los tres criterios, calculado por separado en urbano y rural; el total es su promedio ponderado por población. Se reporta además el indicador **conjunto** (hogares que cumplen los tres a la vez).
- **Factor de expansión:** [factor de personas del capítulo 200 / factor del hogar × miembros del hogar]. Resultados en % de población.
- **Precisión:** error estándar por linealización de Taylor, con departamento × área como estrato y el conglomerado como unidad primaria de muestreo (ver Limitaciones). Estimaciones con CV > 15% se marcan como referenciales (criterio MVCS/INEI).
- **Comparación 2019 vs [AÑO FINAL]:** diferencia en puntos porcentuales y prueba de significancia al 95%.
- **Sensibilidad:** continuidad con umbrales de 24 h (principal), 20 h y 12 h.

### Limpieza

[Completar con `datos/procesados/reporte_limpieza.csv`: registros iniciales, duplicados eliminados, hogares sin fuente de agua, horas o cloro inválidos, hogares con red sin prueba de cloro, registros finales y población expandida por año.]

### Validación

[Completar con `datos/procesados/validacion.csv`: cifra propia vs. cifra oficial del MVCS e INEI y diferencia en pp.]

## 4. Hallazgos principales

[Redactar a partir de `datos/procesados/hallazgos_borrador.md`, con cifras verificadas.]

1. **[Evolución del ODS 6.1.1 entre 2019 y AÑO FINAL]**
2. **[El cuello de botella es distinto en la ciudad y en el campo]**
3. **[Brechas departamentales y criterio limitante por departamento]**

## 5. Limitaciones

- **Calidad medida con cloro:** el cloro residual indica desinfección, no ausencia de contaminación fecal (el JMP usa pruebas de E. coli). La muestra se toma del caño o del recipiente donde el hogar almacena el agua, y solo existe si el hogar aceptó la prueba.
- **Red pública rural:** la ENAPRES cuenta como red pública los sistemas de organizaciones comunales aunque el agua no sea tratada.
- **Continuidad declarada** por el informante, no medida.
- **2020 y 2021 excluidos:** por la pandemia, el INEI redujo el cuestionario y aplicó entrevistas telefónicas, sin poder medir el cloro en el hogar; el MVCS usó factores de expansión calibrados para esos años.
- **Precisión:** la ENAPRES tiene inferencia nacional y departamental por área; las cifras con CV > 15% son referenciales.
- **Diferencias con el JMP:** distintas definiciones de calidad (cloro vs. E. coli) y de disponibilidad (24 h vs. "cuando se necesita"), por lo que las cifras no son directamente comparables.
- **Urbano/rural:** según el umbral de 2000 habitantes del centro poblado.
- **Estrato de diseño aproximado:** los microdatos publicados no incluyen la variable de estrato del diseño muestral (la variable ESTRATO es el estrato socioeconómico A–E y está vacía en el área rural). Se usa departamento × área como pseudo-estrato y CONGLOMERADO como unidad primaria. Los errores estándar y CV son una aproximación y podrían diferir algo de los del INEI.

## 6. Enlaces

- Dashboard: [enlace]
- Publicación en LinkedIn: [enlace]

## 7. Cómo reproducir el proyecto

```bash
pip install -r requirements.txt

# 0) (opcional) Probar el flujo con datos falsos
python scripts/generar_prueba.py
python scripts/procesar_datos.py --config-dir datos/prueba/config
python scripts/analizar_datos.py --base 2019
rm -r datos/procesados/*        # limpiar antes de usar los datos reales

# 1) Obtener datos: completar codigo_encuesta y modulos en config/anios/<año>.json
python scripts/obtener_datos.py --anios 2019 2022 2023 2024 2025 --dry-run
python scripts/obtener_datos.py --anios 2019 2022 2023 2024 2025

# 2) Limpiar y construir variables (verificar antes los nombres en config/)
python scripts/procesar_datos.py

# 3) Indicadores, comparación, validación y datos para la web
python scripts/analizar_datos.py --base 2019
```

Los microdatos no se suben al repositorio por su tamaño; se descargan con el paso 1.

## 8. Uso de inteligencia artificial

[Ajustar a lo que realmente hiciste.] Se usó Claude (claude.ai y Claude Code) para buscar fuentes y fichas metodológicas, escribir y depurar los scripts de procesamiento y análisis, y diseñar el dashboard. Las variables, cifras e interpretaciones fueron verificadas contra el diccionario de la ENAPRES y contra las publicaciones oficiales del MVCS y del INEI.
