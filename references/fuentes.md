# Fuentes y dónde descargar

## ENAPRES (INEI): microdatos
- Portal: https://proyectos.inei.gob.pe/microdatos/ → Encuesta ENAPRES → año → módulo de vivienda y hogar (capítulo 100).
- Descarga también el diccionario de datos y el cuestionario. De ahí salen los nombres reales de variables y códigos para `config/enapres_config.json`.
- Variables a ubicar: factor de expansión del hogar, miembros del hogar, estrato y conglomerado (diseño muestral), área, ubigeo, fuente de agua, días por semana y horas por día con agua, y el resultado de la prueba de cloro residual libre (en la ficha del MEF del PP 0082 se cita como pregunta 129D del capítulo 100).

## Metodología oficial de los indicadores (cómo se calcula la cobertura)
- MVCS / MEF, fichas técnicas de indicadores de brecha (Formato 04-A), con las preguntas exactas de la ENAPRES para cobertura, continuidad y cloro:
  https://www.mef.gob.pe/contenidos/inv_publica/docs/pmi/brecha/formato/29_FORMATO_MVCS.pdf
- INEI, fichas técnicas de indicadores de saneamiento básico de la ENAPRES (documento metodológico):
  https://proyectos.inei.gob.pe/iinei/srienaho/Descarga/DocumentosMetodologicos/2014-18/07_F_SANEAMIENTO_BASICO_2014.pdf
- Resumen: cobertura = P129G ∈ {1, 2, 3}; continuidad = P130 = 1 y P130A = 24; cloro adecuado = P129D ≥ 0,5 mg/L entre hogares con red pública y prueba realizada. Los resultados de población se obtienen trasladando el dato del hogar (capítulo 100) a los residentes (capítulo 200) con su factor de expansión.

## Reportes para validar (réplica)
- INEI, *Perú: Formas de Acceso al Agua y Saneamiento Básico* (boletín con ENAPRES). Todas las ediciones:
  https://www.inei.gob.pe/biblioteca-virtual/boletines/formas-de-acceso-al-agua-y-saneamiento-basico-9343/
- Edición Nro 11 (dic. 2024): https://www.gob.pe/en/institucion/inei/informes-publicaciones/6313803-peru-ways-of-access-to-water-and-basic-sewerage-no-11
- Ojo: el boletín usa años móviles (p. ej. octubre 2022 – setiembre 2023). Para replicar exacto, filtra los meses de encuesta del mismo período, o compara con el cuadro de año calendario.

## JMP: ODS 6.1.1 (contraste)
- Serie total, urbana y rural: `python scripts/obtener_datos.py --wb` (API del Banco Mundial, indicadores SH.H2O.SMDW.ZS, SH.H2O.SMDW.UR.ZS y SH.H2O.SMDW.RU.ZS).
- Tres criterios por área: https://washdata.org → Data → Downloads → archivo de país del Perú (households). Copia accesible, disponible y libre de contaminación por año y área a `references/jmp_peru_criterios.csv`, con el mismo formato que `valores_referencia.csv` (tipo = contraste, indicadores `jmp_accesible`, `jmp_disponible`, `jmp_libre_contaminacion`).
- En el archivo de país, revisa qué encuesta y qué prueba usó el JMP para la calidad en el Perú. Eso explica por qué su cifra rural difiere tanto de la del cloro del INEI.

## Diferencias de definición JMP vs ENAPRES (para la sección de limitaciones)

| Criterio | JMP | Este proyecto (ENAPRES) |
|---|---|---|
| Accesible | Fuente mejorada en la vivienda o terreno (incluye no entubadas) | Red pública dentro de la vivienda |
| Disponible | Cantidad suficiente cuando se necesita | 7 días y 24 horas |
| Calidad | Libre de contaminación fecal y química prioritaria | Cloro residual libre ≥ 0,5 mg/L |
| Agregación | Mínimo de los 3 criterios por área | Mínimo (comparable) y conjunto por hogar (más exigente) |

## Indicador 6.1.1 oficial del MVCS con ENAPRES (réplica principal)
- El Plan Nacional de Saneamiento 2022-2026 define el 6.1.1 como la proporción de población con agua gestionada de forma segura, tomando el menor indicador entre acceso, continuidad de 24 horas y calidad del agua, con datos de la ENAPRES:
  https://cdn.www.gob.pe/uploads/document/file/2648841/Plan%20Nacional%20de%20Saneamiento%202022-2026%20vf.pdf.pdf?v=1640345909
- Serie 2018–2023 (MVCS-DGPRCS, presentación de abril 2025): 40.5, 41.5, 39.6, 38.5, 36.5, 34.5; en 2023, 42.1 urbano y 3.0 rural. 2020 y 2021 se calcularon con factor de expansión calibrado:
  https://intranet.mesadeconcertacion.org.pe/storage/documentos/2025-05-05/ppt-agenda-de-accion-por-el-agua-ods-60.pdf
- Nota: el ODS 6.1.1 en los documentos del MVCS se registra en validar.py con el código ods611_jmp por compatibilidad; compáralo con tu ods611_minimo y, si no coincide, prueba con ods611_conjunto.

## INEI – Acceso a los servicios básicos en el Perú (ENAPRES), contraste
- Año móvil julio 2025 – junio 2026 (preliminar), con la columna de julio 2024 – junio 2025: Cuadro 1.1 (hogares con red pública) y Cuadro 1.5 (hogares con cloro adecuado).
  https://www.gob.pe/institucion/inei/informes-publicaciones/8546395-acceso-a-los-servicios-basicos-en-el-peru-ano-movil-julio-2025-junio-2026
- Edición anual 2024 (enero–diciembre): https://www.gob.pe/institucion/inei/informes-publicaciones/6847826-acceso-a-los-servicios-basicos-en-el-peru-2024
- Ojo: estas cifras son **% de hogares**. El cloro adecuado usa como denominador los hogares con prueba realizada, con cualquier fuente de agua. Con esa definición, los microdatos reproducen la edición anual de 2023 (urbano 43,3) y de 2024 (nacional 37,3; red pública 90,4). Los indicadores del 6.1.1 de este proyecto son % de personas.
