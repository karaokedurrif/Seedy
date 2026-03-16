Qué está bien de lo que tienes ahora

Para consultas tipo:

“¿Qué razas de cerdo ibérico existen?”

“¿Qué gallinas ponedoras recomiendas?”

es normal que no salte web si Qdrant ya responde bien.
Eso está correcto.

Pero si quieres que Seedy esté realmente al día, no puedes depender solo de que una query falle para ir a buscar fuera.

Qué cambiaría
1. Separar “responder bien hoy” de “mantenerse actualizada”

Necesitas dos circuitos distintos:

A. Circuito online de respuesta

El que ya tienes:

query

rewrite

classify

Qdrant

rerank

LLM

fallback web si falta info

B. Circuito offline de actualización

Nuevo:

cada X horas o 1 vez al día

buscar novedades por temas

descargar / limpiar / clasificar

chunkear

embebder

indexar en Qdrant

marcar freshness y fuente

Ese segundo circuito no debe esperar a que un usuario pregunte.

2. No haría “buscar todo agrotech cada 24h” a lo bruto

Eso sería caro, ruidoso y poco útil.
Haría una vigilancia temática por verticales.

Ejemplo de buckets:

genética animal

avicultura

porcino

bovino

bienestar animal

bioseguridad

normativa UE/España

PAC / ayudas

alimentación animal

sensores / IoT / automatización

mercado / exportación

startups / inversión agtech

papers científicos

Y dentro de cada bucket:

fuentes semilla

queries persistentes

frecuencia distinta

Ejemplo:

normativa: cada 12–24h

papers: cada 24–72h

mercado: cada 24h

razas/programas de cría: semanal

fichas técnicas estables: mensual

3. Haría un “freshness index” separado del corpus base

No mezcles igual:

corpus canónico estable

documentos frescos de web

Yo tendría al menos 3 capas en Qdrant:

core_corpus

Documentos lentos y fiables:

programas de cría

catálogos raciales

normativa consolidada

dossiers internos

papers muy relevantes

fresh_web

Contenido reciente:

noticias

nuevas guías

cambios regulatorios

comunicados

ferias

papers nuevos

informes sectoriales

volatile_signals

Muy efímero:

convocatorias

precios

alertas sanitarias

eventos

posts corporativos

Luego en retrieval ponderas distinto:

si la pregunta es estable → pesa más core_corpus

si pide actualidad → pesa más fresh_web

si pide “hoy/último/actual” → activa freshness fuerte

4. El fallback por “RAG insuficiente” no basta

Ahora mismo el sistema piensa:

“si Qdrant devuelve 20 resultados, ya estoy cubierto”

Pero eso puede ser falso.

Puedes tener 20 resultados muy buenos… y aún así estar desactualizado.

Ejemplo:

“normativa de bienestar para gallinas”

Qdrant devuelve buen material de hace 2 años

no falla el recall

pero falta la actualización reciente

Solución

Añade una decisión extra:

¿la pregunta requiere actualidad?

¿la respuesta depende de algo que puede haber cambiado?

Si sí:

busca en web aunque Qdrant tenga resultados.

O sea, además del fallback por insuficiencia, necesitas web augmentation por frescura.

5. Añadir detección de “temporalidad”

Esto te daría muchísimo valor.

Clasifica cada query también por:

stable

semi_dynamic

dynamic

breaking

Ejemplos:

stable

“qué es consanguinidad”

“qué razas de Bresse existen”

“qué es un cruce terminal”

semi_dynamic

“qué programas de cría hay para ibérico”

“qué ayudas hay para extensivo”

“qué líneas genéticas se usan más”

dynamic

“últimas ayudas”

“nueva normativa”

“precios”

“qué empresas están lanzando sensores”

“qué papers nuevos hay”

breaking

brotes sanitarios

restricciones regulatorias

cierres de mercado

aranceles

alertas alimentarias

Regla simple:

stable → Qdrant primero

dynamic o breaking → web primero o web obligatoria

6. Haría “búsquedas programadas”, no solo crawl libre

No rastrearía internet sin control.
Tendría dos mecanismos:

A. Search-driven ingestion

Cada día lanzas queries como:

“site:efsa.europa.eu poultry welfare report”

“site:mapa.gob.es porcino extensivo”

“site:ec.europa.eu animal welfare regulation poultry”

“broiler slow growth genetics study”

“capon production free range study”

B. Source-driven crawl

Fuentes concretas y buenas:

MAPA

BOE

EUR-Lex

EFSA

FAO

revistas científicas

asociaciones de raza

centros de investigación

universidades

ferias relevantes

medios sectoriales fiables

Eso da mucha más señal que un SearXNG solo reactivo.

7. Pondría prioridades de fuente

No todo “agrotech” vale lo mismo.
Yo asignaría score de autoridad:

1.0 → normativa oficial, organismos públicos, papers revisados

0.9 → universidades, centros de investigación, asociaciones oficiales

0.7 → medios sectoriales buenos

0.5 → blogs técnicos

0.3 → marketing comercial

0.1 → foros / ruido

Y usaría eso:

al indexar,

al rerankear,

al decidir si una novedad entra o no al corpus.

8. No todo lo nuevo debe entrar a Qdrant

Otro error común es meter todo lo que se encuentra.
No. Antes de indexar, pasa un filtro:

relevancia temática

autoridad de fuente

novedad real vs duplicado

calidad textual

idioma

compatibilidad con taxonomía

Si no pasa, no entra.

9. Añadir deduplicación y canonicalización

En agrotech la misma noticia o nota aparece replicada por:

prensa,

distribuidores,

asociaciones,

medios,

notas de empresa.

Antes de indexar:

hash del contenido,

clustering semántico,

elegir canonical source,

guardar referencias duplicadas como fuentes secundarias.

10. Guardar “freshness metadata” útil

A cada chunk/doc le pondría:

published_at

discovered_at

source_authority

topic

country

species

doc_type

freshness_tier

canonical_url

is_regulatory

is_scientific

is_market_signal

Eso luego te deja rerankear muy bien.

11. Añadir consultas persistentes tipo “watchlist”

En vez de esperar preguntas de usuario, define una watchlist.

Ejemplo:

Avicultura

slow-growing broiler genetics

free-range poultry welfare regulation

native chicken breeds conservation

capon production study

Porcino

iberian pig genetics

outdoor pig production

swine biosecurity update

pig welfare regulation

Bovino

suckler cow extensivo Spain

beef cattle crossbreeding Spain

inbreeding cattle local breeds

dehesa beef market

Agtech puro

livestock precision farming

poultry vision AI breed classification

pig monitoring sensors

farm automation startup Europe

Cada una con frecuencia.

12. Haría crawling incremental, no total

Si usas crawl4ai:

solo páginas nuevas o cambiadas

respetando sitemaps/RSS si existen

detectando cambios por hash/etag

evitando reindexar todo

13. Métrica que sí miraría

No “cuántas búsquedas web se dispararon”.

Eso solo te dice actividad, no calidad.

Miraría esto:

de actualización

docs nuevos útiles por día

% de docs aceptados tras filtrado

tiempo medio hasta indexación

duplicados evitados

cobertura por topic

de respuesta

% de queries “dynamic” que usaron fresh layer

mejora en precisión con fresh docs

citas a fuentes recientes

ratio de respuestas con evidencia desactualizada

de salud

temas sin novedades en X días

fuentes rotas

feeds muertos

dominios que bajaron calidad

14. Mi recomendación concreta para Seedy

Yo dejaría esto:

Online

Qdrant híbrido

reranker

web augmentation cuando:

la query sea temporal,

el dominio sea cambiante,

o el critic detecte posible desactualización

Offline diario

jobs temáticos

búsquedas persistentes

crawl de fuentes semilla

ingestión selectiva

indexado en fresh_web

Offline semanal

consolidación:

lo más valioso pasa de fresh_web a core_corpus

lo efímero caduca o baja de peso

15. Regla simple para empezar ya

Si quieres una mejora rápida y útil:

Mantén el fallback actual

pero añade:

Un job diario que haga esto

recorra 20–50 queries temáticas fijas

consulte 20–30 fuentes prioritarias

descargue solo novedades

filtre por calidad

indexe en una colección fresh_web

marque metadatos temporales

caduque lo irrelevante a los 30–90 días

Eso ya te cambia muchísimo la actualización real.