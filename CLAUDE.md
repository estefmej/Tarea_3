# Instrucciones para Claude Code – Tarea 3 (Parte 1)

## Contexto
Proyecto: ODS 6.1.1 (agua gestionada de forma segura) en el Perú con microdatos de la ENAPRES (INEI).
Pregunta: qué criterio (acceso en la vivienda, continuidad 24 h, cloro ≥ 0,5 mg/L) limita el indicador y cómo cambió entre 2019 y el último año, por área y departamento.
Metodología y fuentes: `README.md` y `references/fuentes.md`. Cifras oficiales para validar: `references/valores_referencia.csv`.

## Flujo (en este orden)
1. `pip install -r requirements.txt` y prueba con datos falsos (ver README, paso 0). Luego borra `datos/procesados/*`.
2. **Códigos de descarga:** para cada año (2019, 2022, 2023, 2024, 2025) obtén del portal de microdatos del INEI el código de la ENAPRES y los módulos del capítulo 100 (vivienda y hogar) y del capítulo 200 (residentes). Anótalos en `config/anios/<año>.json`. Si el portal no se puede leer automáticamente, pide al usuario que copie el enlace de descarga (clic derecho → copiar dirección). Confirma si la ENAPRES 2025 ya está publicada; si no, el año final es 2024.
3. `python scripts/obtener_datos.py --anios ...` (primero con `--dry-run`).
4. **Verificar variables con el diccionario y el cuestionario de cada año** (vienen en el zip o en la documentación del portal). Confirma nombres y códigos de: llaves del hogar, factor, miembros, estrato, conglomerado, área, ubigeo, resultado de la entrevista, P129G, P130, P130A, P129D (¿numérica en mg/L o categórica?). Las diferencias por año van en `config/anios/<año>.json`. Usa el capítulo 200 si es posible (`personas.archivo`), que es el método oficial.
5. `python scripts/procesar_datos.py` → revisa `datos/procesados/reporte_limpieza.csv` (duplicados, exclusiones, población expandida razonable ~33–34 millones).
6. `python scripts/analizar_datos.py --base 2019` → revisa `validacion.csv`.
   - Si una réplica sale REVISAR: comprueba año calendario vs año móvil, denominador, peso (persona vs hogar), códigos. Compara `ods611_minimo` con `ods611_minimo_directo` para ver cuál reproduce al MVCS y documenta cuál se usa.
   - No ajustes la metodología solo para "hacer coincidir" una cifra: documenta la diferencia y su causa probable.
7. Redacta los tres hallazgos en el README a partir de `hallazgos_borrador.md`: cifra + interpretación + significancia + confiabilidad (CV). Completa las secciones de limpieza y validación con tablas reales.

## Reglas
- **Nunca inventes cifras.** Todo número del README y del dashboard sale de los archivos de `datos/procesados/`.
- No uses 2020 ni 2021 (entrevista telefónica sin medición de cloro).
- No destaques estimaciones con CV > 15%; si aparecen, márcalas como referenciales.
- No subas microdatos a git (`.gitignore`); sí sube `datos/procesados/` livianos y `web/data/`.
- Antes de cambiar una definición de indicador, consulta al usuario.
