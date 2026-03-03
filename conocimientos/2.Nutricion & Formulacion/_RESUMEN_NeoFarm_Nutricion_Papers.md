# NeoFarm — Resumen Nutrición y Papers Científicos
## Documento índice para RAG — Colección "Nutrición & Formulación"

---

## Paper: Butirato Sódico en Nutrición Porcina (Burlakova & Dimitrov, 2025)
**Archivo original**: Sodium_Butyrate_in_Pig_Nutrition.pdf
**DOI**: 10.20944/preprints202511.1328.v1

### Qué es el butirato sódico
Sal sódica del ácido butírico (C4H7NaO2). Polvo cristalino blanco, altamente soluble en agua (>330 g/L). Punto de fusión 250-253°C. Se usa como aditivo funcional en piensos porcinos como alternativa a antibióticos promotores de crecimiento.

### Efectos sobre inmunidad intestinal
- **Barrera intestinal**: El butirato refuerza las uniones estrechas (tight junctions) del epitelio intestinal, estimula producción de mucina y secreción de péptidos antimicrobianos.
- **Inmunoglobulinas**: La suplementación en cerdas aumenta IgA en calostro, mejorando inmunidad pasiva de los lechones lactantes.
- **Respuesta inmune sistémica**: Aumenta IgG e IgA en suero y en tejidos yeyunales.
- **Anti-inflamatorio**: Inhibe activación de mastocitos, suprime liberación de histamina, triptasa, y citoquinas pro-inflamatorias (TNF-α, IL-6).
- **Células goblet**: Los cerdos alimentados con butirato protegido muestran más células goblet y células secretoras de mucina en el íleon.

### Efectos sobre crecimiento y rendimiento
- Mejora la ganancia media diaria (GMD/ADG) y el índice de conversión (FCR).
- Promueve la proliferación de células intestinales y renovación del epitelio.
- Mejora la digestibilidad de nutrientes.

### Efectos sobre microbioma
- Fuente de energía primaria para colonocitos.
- Modula composición microbiana intestinal favoreciendo bacterias beneficiosas.
- Reduce compuestos tóxicos de fermentación proteolítica (amoniaco, fenoles, indoles).
- El NH3 derivado de la fermentación proteica es uno de los principales olores en granjas porcinas. Niveles óptimos: 10-25 ppm.

### Aplicación práctica en PorciData
- Integración con Capa 6 (BME688 nariz electrónica): si VOC score alto + NH3 alto → considerar suplementación con butirato sódico.
- Integración con módulo Nutrición: añadir butirato como ingrediente en el solver LP con restricción de inclusión máxima.

---

## Paper: Enzimas NSP en Nutrición Porcina (Yamsakul et al., 2025)
**Archivo original**: Enzymes_in_Enhancing_pigs.pdf
**DOI**: 10.20944/preprints202511.2029.v1

### Qué son las enzimas NSP
Enzimas exógenas que degradan polisacáridos no amiláceos (NSP) presentes en ingredientes fibrosos (cebada, trigo, salvado, subproductos). Los cerdos no producen estas enzimas naturalmente.

### Hallazgos principales
- La suplementación con enzimas NSP mejora la digestibilidad de materia seca, proteína cruda, grasa cruda, fibra cruda y cenizas, especialmente en dietas de acabado (finisher) y gestación/lactación.
- Mejora la morfología intestinal: vellosidades más altas, criptas más profundas, mayor área de absorción en yeyuno e íleon.
- Efectos más pronunciados cuando las dietas contienen niveles sustanciales de NSP.
- La variabilidad en respuestas sugiere que la efectividad depende de la composición de la dieta, la salud del cerdo y el entorno intestinal.

### Aplicación práctica en PorciData
- En el módulo Nutrición: añadir enzimas NSP como ingrediente/aditivo cuando la formulación LP incluya >15% de ingredientes fibrosos.
- Ahorro típico estimado: 3-5% en coste de pienso por mejor aprovechamiento nutricional.

---

## Modelo Nutricional: NRC 2012

### Sistemas de energía
- **NRC 2012** (USA): Sistema Energía Neta (NE). Recomendado como base para PorciData. Open source, bien documentado.
- **INRA/Systali** (Francia): EN similar pero coeficientes franceses. Alternativa para mercado EU.
- **CVB** (Holanda): Energía Digestible + factores. Usado por Topigs/DanBred.

### Formulación por Programación Lineal
Solver: HiGHS (open source) o javascript-lp-solver (WASM).
Minimizar coste sujeto a 20-40 restricciones nutricionales por fase.
Inputs: composición nutricional de ingredientes + precios actualizados + requerimientos por fase (NRC 2012).

### Lonjas de precios (fuentes de datos)
- **Mercolleida**: Referencia porcino España (semanal)
- **Lonja de Segovia**: Vacuno y cordero (semanal)
- **Lonja del Ebro**: Cereales y materias primas

### Innovaciones únicas PorciData en Nutrición
1. Terminal Bloomberg-style de commodities agrícolas
2. Reformulación automática cuando IoT detecta estrés (T° alta → subir energía neta +10%, Lys +15%)
3. Oligoelementos inteligentes: Selenio + Vit E automáticos cuando vocalizaciones estrés (Capa 2 acústica)
4. Predicción de precios con IA para hedging financiero
