---
module: genetica
especie: bovino
sistema: extensivo
razas_objetivo: [Avileña, Retinta, Morucha, Rubia Gallega, Pirenaica, Asturiana]
motor_genetico: [Wright, BLUP, Heterosis, Apareamiento_Optimo]
integracion: [FarmMatch, Genomica, DigitalTwin]
version: 2026
---

# BLOQUE 1 — OBJETIVO GENÉTICO EXTENSIVO

[META]
tipo: estrategia

Prioridades:
- Fertilidad
- Facilidad de parto
- Longevidad funcional
- Adaptación climática
- Resistencia parásitos
- Robustez en pasto

Alineado con modelo extensivo :contentReference[oaicite:3]{index=3}

---

# BLOQUE 2 — RASGOS PRIORITARIOS

[META]
tipo: rasgos_clave

## 2.1 Reproductivos
- Intervalo entre partos
- % preñez
- Días abiertos
- Facilidad parto

## 2.2 Productivos
- Peso al destete (205 días)
- Peso al año (365 días)
- Ganancia media diaria en pasto

## 2.3 Adaptativos
- Resistencia estrés térmico
- Docilidad
- Supervivencia terneros

---

# BLOQUE 3 — CONSANGUINIDAD

[META]
tipo: control_inbreeding

Uso crítico en:
- Razas autóctonas
- Poblaciones pequeñas

Simulación:
- 3–5 generaciones
- Impacto en fertilidad
- Riesgo depresión endogámica

---

# BLOQUE 4 — HETEROSIS

[META]
tipo: cruzamientos

Aplicaciones:
- Angus × Holstein
- Charolais × Autóctona
- Cruces rotacionales

Impactos esperados:
- ↑ fertilidad
- ↑ vigor híbrido
- ↓ mortalidad neonatal

---

# BLOQUE 5 — GENÓMICA BOVINA

[META]
tipo: genomica

Paneles:
- GGP-9K
- GGP-100K
- Igenity Beef

Usos:
- GEBVs jóvenes
- Eliminación portadores
- Aumento precisión selección
- Ranking percentil dentro raza

---

# BLOQUE 6 — APAREAMIENTO ÓPTIMO EXTENSIVO

[META]
tipo: optimizacion

Objetivo:
Maximizar resiliencia + fertilidad
Minimizar consanguinidad

Variables adicionales:
- Proximidad geográfica (transporte toro)
- Adaptación clima similar
- Índice económico extensivo

---

# BLOQUE 7 — DIGITAL TWIN GENÉTICO

[META]
tipo: simulacion

Entidades:
- Animal
- Lote
- Parcela

Modelos:
- Predicción fallo reproductivo
- Impacto THI acumulado
- Simulación carga ganadera futura

---

# BLOQUE 8 — BENCHMARKING

[META]
tipo: comparativa

Comparaciones:
- Media raza
- Cooperativa
- Histórico propio

Outputs:
- Tendencia genética anual
- Top 10 reproductores
- Alertas consanguinidad estructural