Lo que mejoraría
1. El rewrite puede sesgar demasiado la búsqueda

Tu ejemplo:

usuario: “¿y para capón?”

rewrite: “Sulmtaler capón gourmet cruces”

Eso puede ser bueno si Sulmtaler ya venía claramente del contexto.
Pero puede ser peligroso si el modelo mete una entidad que no estaba confirmada.

El mayor fallo que veo en sistemas así es este:

el rewrite no solo resuelve la elipsis,

también inyecta hipótesis.

Y entonces el buscador deja de buscar “capón” y empieza a buscar “Sulmtaler”, aunque quizá el usuario quería comparar otra cosa.

Cómo lo haría mejor

Guardaría dos queries:

query original contextualizada mínima

query expandida

Ejemplo:

q1: “capón gourmet en extensivo”

q2: “Sulmtaler capón gourmet cruces”

Y recuperaría con ambas.

Eso te da:

más recall,

menos riesgo de overfitting al rewrite.

2. La clasificación no debería ser monolítica

Pones:

AVICULTURA → buscar en [avicultura, genética]

Eso está bien, pero yo no haría clasificación “una sola etiqueta”.
En agrotech muchas consultas son multietiqueta.

Ejemplos:

“capón gourmet en extensivo” = avicultura + genética + mercado + manejo

“ibérico, consanguinidad y desarrollo de mercado” = genética + porcino + mercado

“bovino de montaña y cruzamientos” = bovino + genética + extensivo

Mejor enfoque

En vez de una clase única, usaría:

top 2–3 categorías con pesos

o un clasificador multilabel

Ejemplo:

avicultura 0.82

genética 0.77

extensivo 0.54

gourmet/mercado 0.33

Y eso luego afecta:

qué colecciones consultas,

cómo ponderas resultados,

qué prompt final eliges.

3. Top 8 tras recuperación es probablemente poco

Esto me parece uno de los puntos más flojos.

Si haces:

hybrid search

top 8

rerank

top 5

te puedes quedar sin recall en consultas complejas.

Para consultas cortas y cerradas puede valer.
Para las tuyas, que muchas veces son:

comparativas,

genéticas,

normativas,

estratégicas,

yo subiría bastante.

Recomendación

Probar algo como:

recuperación híbrida: top 30–50

rerank: top 15–25

contexto final: 5–8 chunks

Eso suele funcionar bastante mejor.

4. El threshold de web fallback parece frágil

Pones:

Web fallback si RRF < 0.012

La idea es buena, pero ese tipo de umbral fijo suele ser inestable.

¿Por qué?
Porque el score de RRF:

depende del tamaño del pool,

de la distribución de scores,

del tipo de consulta,

del idioma,

de si hay entidades raras.

Un umbral fijo puede provocar:

demasiadas búsquedas web,

o casi ninguna.

Mejor que un único threshold

Usaría una decisión combinada:

score del top 1,

gap entre top 1 y top 5,

presencia de entidades reconocidas,

si el clasificador detecta “consulta reciente / de actualidad / normativa cambiante”,

si hay muy baja cobertura de categorías esperadas.

Ejemplo de fallback:

si top1 bajo,

y top5 muy plano,

y no hay coincidencias léxicas fuertes,

entonces web.

Eso es mucho más robusto que RRF < X.

5. Falta diversificación antes del LLM

Puedes tener top 5 muy redundante:

3 chunks del mismo documento,

2 del mismo tema,

todos dicen lo mismo.

Eso es malísimo para RAG.

Añadiría una capa de diversidad

Antes de inyectar los 5 chunks:

máximo 2 chunks por documento,

máximo 1 chunk por sección si son casi iguales,

bonus por cubrir subaspectos distintos.

Para tus casos, eso importa mucho:

genética,

manejo,

mercado,

normativa,

comparación racial.

No quieres 5 chunks repitiendo “la raza Prat tiene interés gastronómico”.

6. 5 chunks puede ser correcto, pero depende del tipo de pregunta

Para preguntas simples, sí.
Para preguntas complejas, quizá no.

Ejemplo:
“hazme una propuesta de hibridación para capón gourmet lento crecimiento en extensivo, con línea paterna, materna y control de consanguinidad”

Eso rara vez queda bien resuelto con solo 5 chunks si no están muy bien elegidos.

Lo haría dinámico

consulta simple: 4–5 chunks

consulta comparativa: 6–8

consulta de planificación: 8–10 con compresión previa

7. Te falta un paso explícito de metadata-aware ranking

En tu dominio los metadatos importan muchísimo:

especie,

raza,

país,

sistema productivo,

idioma,

tipo documental,

año,

autoridad,

experimental vs normativa,

extensivo vs intensivo.

Yo no dejaría todo al embedding + BM25 + reranker.

Añadiría bonus o filtros por metadata

Ejemplos:

si la query dice “capón” → bonus aviar

si dice “extensivo” → penaliza intensivo

si dice “España” → bonus fuentes españolas

si dice “genética” → bonus estudios, programas de cría, papers

si dice “mercado” → bonus informes sectoriales

Eso en verticales funciona muy bien.

8. Te falta query decomposition para preguntas complejas

Ahora tu pipeline parece asumir una sola query principal.

Pero muchas preguntas tuyas reales son compuestas:

“porcino extensivo, consanguinidad, temas genéticos, posibilidades de desarrollar este mercado”

“razas de gallinas y sus posibilidades para hibridación de un capón gourmet en extensivo”

Eso son varias subpreguntas.

Mejor enfoque

Antes de buscar:

detectar si la query es compuesta,

descomponer en 2–4 subconsultas,

recuperar por cada una,

fusionar,

rerankear globalmente.

Ejemplo:
“capón gourmet extensivo lento crecimiento”
se divide en:

razas cárnicas lentas

esquemas de hibridación

caponización/calidad de canal

sistemas extensivos/gourmet

Eso mejora muchísimo la cobertura.

9. Cuidado con usar un único prompt por categoría

Está bien tener prompt por categoría, pero aún mejor:

prompt base por categoría

instrucciones extra por intención

Porque no es igual:

explicar,

comparar,

recomendar,

diseñar programa genético,

resumir normativa.

10. Falta observabilidad clara

Tu arquitectura tiene buena pinta, pero para saber si funciona de verdad necesitas registrar:

query original,

rewrite,

categorías predichas,

docs recuperados,

scores BM25/dense/RRF/reranker,

chunks finales usados,

si hubo fallback web,

feedback del usuario.

Sin eso, es muy difícil depurar.