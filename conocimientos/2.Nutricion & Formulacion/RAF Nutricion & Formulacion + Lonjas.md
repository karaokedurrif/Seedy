---
collection: NeoFarm — Nutrición & Formulación
type: RAF_precio_lonjas
version: 1.0
scope: vacuno_extensivo + porcino_intensivo
role: integración_precio_en_solver
---

# RAF — Nutrición & Formulación con Resumen de Lonjas

## 1️⃣ PROBLEMA ACTUAL

Existe un archivo:

- cruces_gourmet_segovia.csv

Pero NO existe:

- Definición de qué lonjas alimentan esos precios
- Frecuencia de actualización
- Distinción vivo vs canal
- Clasificación EUROP asociada
- Uso explícito en el LP Solver

Actualmente el solver minimiza coste de dieta,
pero no maximiza margen final.

---

# 2️⃣ DEFINICIÓN DE LONJA EN CONTEXTO NEOFARM

Una lonja es:

Mercado de referencia regional donde se publican precios
semanales para:

- Terneros vivos
- Añojos canal
- Vacas desvieje
- Cerdos cebo
- Lechones

Ejemplos relevantes para Segovia:

- Lonja Salamanca
- Lonja León
- Lonja Segovia
- Lonja Mercolleida (porcino referencia nacional)

Frecuencia típica:
- Semanal (jueves/viernes)

Unidad:
- €/kg vivo
- €/kg canal

---

# 3️⃣ MODELO DE DATOS PROPUESTO

Crear tabla:

market_prices

Campos:

- id
- species (bovine|porcine)
- category (ternero_vivo, añojo_canal, vaca, cerdo_cebo...)
- europ_class (U,R,O,...)
- price_per_kg
- unit (live|carcass)
- source_lonja
- week_number
- year
- region

Esto permite:

✔ Histórico
✔ Media móvil
✔ Tendencia
✔ Volatilidad

---

# 4️⃣ INTEGRACIÓN EN EL LP SOLVER

## 4.1 Estado actual del solver

Minimiza:

Min Σ (coste_ingrediente_i × inclusion_i)

Sujeto a:

- Energía mínima
- Proteína mínima
- Fibra máxima
- Minerales
- Límites inclusión

Pero NO considera:

- Precio final del animal
- Clasificación canal esperada
- Penalizaciones por engrasamiento

---

## 4.2 Solver con función objetivo económica real

Nueva función objetivo:

Maximizar Margen Esperado

Margen = Precio_esperado_animal
         − Coste_alimentación
         − Coste_fijo_día × días_engorde

Donde:

Precio_esperado_animal =
  Peso_canal_estimado × Precio_lonja_categoria

Peso_canal_estimado =
  Peso_vivo × Rendimiento_canal(raza/cruce)

---

# 5️⃣ CONEXIÓN CON GENÉTICA (VacasAPP)

Del modelo genético :contentReference[oaicite:3]{index=3}:

- Marbling
- Rendimiento canal
- Crecimiento
- Rusticidad

Permite estimar:

- Ganancia diaria esperada
- Rendimiento canal %
- Clasificación EUROP probable

Por ejemplo:

Cruce Avileña × Limusina
  Rendimiento esperado: 60-63%

Cruce Avileña pura
  Rendimiento esperado: 55-58%

Si la lonja paga:

- U: 7.5 €/kg
- R: 7.2 €/kg
- O: 6.5 €/kg

Entonces el solver puede:

Optimizar dieta para alcanzar
peso objetivo antes de perder categoría.

---

# 6️⃣ CASO VACUNO EXTENSIVO — SEGOVIA

Según datos económicos :contentReference[oaicite:4]{index=4}:

Añojos <24 meses:
- 7.0–7.5 €/kg canal

Novillos >24 meses:
- 5.0 €/kg canal

Por tanto:

Existe penalización fuerte al superar 24 meses.

El solver debe incorporar:

Restricción:

edad_sacrificio ≤ 24 meses

o penalización en función objetivo.

---

# 7️⃣ CASO PORCINO INTENSIVO

En porcino:

Mercolleida referencia semanal.

Categorías:

- Cerdo cebo 100 kg
- Lechón 20 kg
- Cerda desvieje

Solver porcino debe considerar:

Precio_cerdo × Peso_final
− Consumo_total_pienso × Precio_pienso

Optimización real:

No solo FCR mínimo,
sino FCR óptimo dado precio mercado.

Si el precio baja,
puede convenir reducir días de cebo.

---

# 8️⃣ PROPUESTA DE ARQUITECTURA

## Módulo nuevo:

/market/

- lonjas_service.ts
- price_ingestion.ts
- margin_engine.ts

Funciones:

getCurrentPrice(species, category, region)

estimateRevenue(animal_profile)

optimizeDietForMargin()

---

# 9️⃣ ROL DE cruces_gourmet_segovia.csv

Ese CSV debería:

Contener:

- Raza padre
- Raza madre
- Peso esperado
- Rendimiento %
- Clasificación EUROP
- Precio estimado canal
- Margen estimado

Pero actualmente no hay metadatos
ni fuente de precio declarada.

Se recomienda añadir columnas:

- source_lonja
- week_reference
- unit
- confidence_score

---

# 🔟 BENEFICIO PARA NEOFARM

Sin lonjas:
  → Optimizas coste nutricional

Con lonjas:
  → Optimizas beneficio real

Eso convierte Nutrición
en módulo económico estratégico.

---

# 11️⃣ CONCLUSIÓN

Integrar precios de lonja permite:

✔ Ajustar días de engorde óptimos  
✔ Evitar penalización por edad  
✔ Decidir vender vivo vs canal  
✔ Ajustar dieta según mercado  
✔ Simular escenarios de precio  

Nutrición deja de ser técnica.
Pasa a ser financiera.

---

FIN RAF