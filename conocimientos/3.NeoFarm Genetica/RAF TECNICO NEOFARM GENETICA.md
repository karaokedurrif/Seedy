---
collection: NeoFarm — Genética
type: RAF_tecnico_complementario
version: 1.0
audience: desarrolladores + data_scientists + arquitectura_IA
related_document: RAF_Genetica_v2
---

# RAF TÉCNICO — NEOFARM GENÉTICA

Este documento define la arquitectura matemática, algorítmica y de datos
del módulo Genética para porcino intensivo y vacuno extensivo.

No describe visión estratégica.
Describe implementación técnica.

---

# 1️⃣ ARQUITECTURA LÓGICA DEL MOTOR GENÉTICO

El motor genético se divide en 5 subsistemas independientes:

1. Pedigree Engine
2. Inbreeding Engine
3. Genetic Merit Engine (EPD/BLUP)
4. Mating Optimization Engine
5. Economic Index Engine

Todos desacoplados del frontend y base de datos.

---

# 2️⃣ MODELO DE DATOS GENÉTICO

## 2.1 Entidad Animal

Campos mínimos requeridos:

- id
- species (bovine | porcine)
- breed
- sire_id
- dam_id
- birth_date
- phenotypes[]
- epds[]
- genomic_test_id
- status

## 2.2 Pedigree Graph

Representación:
Directed Acyclic Graph (DAG)

Restricción:
No permitir ciclos (validación al insertar).

Profundidad:
Mínimo 3 generaciones obligatorias para cálculo F robusto.
Ideal: 5 generaciones.

---

# 3️⃣ CÁLCULO DE CONSANGUINIDAD (WRIGHT F)

Algoritmo:
Meuwissen & Luo (1992) — Tabular Method

F = Σ(1/2)^(n1+n2+1) (1 + FA)

Donde:
- n1 = generaciones hasta ancestro común vía padre
- n2 = generaciones vía madre
- FA = coeficiente ancestro común

Complejidad:
O(n^2) sobre matriz de parentesco.

Optimización:
Memoización de coeficientes ya calculados.

Umbrales dinámicos:
Porcino intensivo:
  Verde < 0.0625
Vacuno extensivo:
  Verde < 0.08
Iberico:
  Verde < 0.10

---

# 4️⃣ MODELO EPD / BLUP SIMPLIFICADO

## 4.1 Modelo Fenotípico

EPD_r = h² * (P_i − μ_grupo) / 2

Donde:
- h² heredabilidad específica por rasgo
- μ_grupo = contemporáneos misma edad/lote

Tabla heredabilidades base:

Vacuno:
- Peso nacimiento: 0.40
- Peso destete: 0.25
- Fertilidad: 0.05–0.10
- Facilidad parto: 0.12

Porcino:
- GMD: 0.30
- FCR: 0.25
- Prolificidad: 0.10
- Robustez inmune: 0.15

---

## 4.2 Integración Genómica

Si hay test SNP:

Accuracy_final =
  sqrt( (1 − r²_parental) + r²_genómico )

EPD_final =
  (EPD_fenotípico * w1 + GE-EPD * w2)

Donde:
w2 > w1 si SNP > 50K

---

# 5️⃣ PREDICCIÓN HETEROSIS

Modelo:

Heterosis_trait =
  H_base_trait * DistanciaGenética(R1,R2)

Distancia genética precargada por matriz de razas.

Ejemplos:

Angus × Autóctona:
  Alta heterosis crecimiento
Holstein × Angus:
  Alta heterosis fertilidad
Large White × Duroc:
  Moderada heterosis FCR

---

# 6️⃣ MOTOR DE APAREAMIENTO ÓPTIMO

Función objetivo:

Maximizar:

Σ (IndiceGenetico_cría)
− λ Σ (F_cría)

Restricciones:

F_cría ≤ F_max
Diversidad mínima de machos
Stock semen disponible

Resolver con:

- Hungarian Algorithm (pequeñas poblaciones)
- MILP con HiGHS (cooperativas grandes)

Output:

{
  female_id,
  male_id,
  expected_F,
  expected_merit,
  heterosis_pct
}

---

# 7️⃣ ÍNDICE ECONÓMICO

MeritScore =
Σ (EPD_estandarizado_i * peso_i)

Pesos dinámicos según perfil:

Vacuno extensivo:
- Fertilidad 30%
- Facilidad parto 20%
- Peso destete 25%
- Resiliencia térmica 15%
- Longevidad 10%

Porcino intensivo:
- FCR 35%
- GMD 25%
- Prolificidad 15%
- Robustez 15%
- Uniformidad 10%

---

# 8️⃣ INTEGRACIÓN CON DIGITAL TWIN

El módulo genético expone:

- Expected Performance Curve
- Risk Index
- Genetic Resilience Score
- Genetic × Environment Interaction (G×E)

Modelo G×E:

Performance_real =
  Genetic_Potential
  × Environmental_Modifier
  × Health_Modifier

---

# 9️⃣ ANALÍTICA AVANZADA FUTURA

Roadmap técnico:

- Bayesian genomic prediction
- Random Forest para G×E
- Integración sensores respiratorios ↔ línea genética
- Simulación multi-generacional Monte Carlo
- Optimización genética bajo cambio climático

---

# 🔟 ESCALABILIDAD

Arquitectura preparada para:

- 10–10.000 animales por granja
- Cooperativas multi-granja
- Benchmarking anonimizado
- Marketplace genético global

---

# CONCLUSIÓN TÉCNICA

NeoFarm Genética no es solo gestión de pedigree.

Es:

- Motor matemático
- Sistema optimizador
- Capa predictiva del Digital Twin
- Infraestructura de mejora genética independiente