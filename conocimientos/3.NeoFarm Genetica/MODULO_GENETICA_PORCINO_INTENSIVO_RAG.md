---
module: genetica
especie: porcino
sistema: intensivo
subtipos: [blanco, iberico]
motor_genetico: [Wright, BLUP, Heterosis, Apareamiento_Optimo]
integracion: [FarmMatch, Banco_Semen, Inseminaciones, Genomica]
version: 2026
---

# BLOQUE 1 — OBJETIVO GENÉTICO PORCINO INTENSIVO

[META]
tipo: estrategia

Objetivos prioritarios:
- Maximizar FCR
- Incrementar GMD
- Aumentar prolificidad
- Reducir mortalidad neonatal
- Mejorar robustez respiratoria
- Optimizar uniformidad de lote

Diferenciación:
- Blanco industrial → eficiencia
- Ibérico → calidad canal + control consanguinidad

---

# BLOQUE 2 — RASGOS PRIORITARIOS

[META]
tipo: rasgos_clave

## 2.1 Maternal
- Nacidos vivos (NV)
- Destetados/camada
- Peso al nacimiento
- Intervalo destete-cubrición
- Tasa retorno a celo

## 2.2 Terminal
- Ganancia Media Diaria
- Conversión Alimenticia
- Espesor grasa dorsal
- % magro
- Índice canal

## 2.3 Robustez
- Índice tos
- Resistencia respiratoria
- Mortalidad transición
- Adaptación térmica

---

# BLOQUE 3 — CONSANGUINIDAD

[META]
tipo: control_inbreeding

Coeficiente Wright:

Umbrales:
- Blanco industrial:
  - <6.25% verde
  - 6.25–12.5% amarillo
  - >12.5% rojo

- Ibérico puro:
  - <10% verde
  - 10–20% amarillo
  - >20% rojo

Uso:
- Alertas automáticas
- Bloqueo de apareamiento
- Simulación 3 generaciones

---

# BLOQUE 4 — HETEROSIS EN CRUCES

[META]
tipo: heterosis

Cruces típicos:
- Large White × Landrace (maternal)
- Landrace × Duroc
- Pietrain × F1

Variables:
- Heterosis crecimiento
- Heterosis prolificidad
- Heterosis robustez

Uso:
- Predicción F1
- Diseño esquema piramidal
- Optimización terminal

---

# BLOQUE 5 — GENÓMICA PORCINA

[META]
tipo: genomica

Fuentes:
- SNP 60K
- Paneles Neogen
- Datos PIC (si cliente)

Aplicaciones:
- Selección temprana reproductoras
- Eliminación portadores
- Mejora eficiencia alimentaria
- Predicción susceptibilidad respiratoria

---

# BLOQUE 6 — APAREAMIENTO ÓPTIMO

[META]
tipo: optimizacion

Función objetivo:
Max(Índice genético) - λ(F)

Variables:
- Índice maternal
- Índice terminal
- Heterosis esperada
- Consanguinidad proyectada

Output:
- Lista parejas óptimas
- F esperado camada
- Mérito económico esperado

---

# BLOQUE 7 — BANCO DE SEMEN

[META]
tipo: gestion_reproductiva

Porcino:
- Vida útil 3–5 días
- Motilidad progresiva %
- Concentración
- Historial fertilidad

Integración:
- Verificación disponibilidad en FarmMatch
- Control rotación genética

---

# BLOQUE 8 — LOOP DE RETROALIMENTACIÓN

[META]
tipo: closed_loop

Comparación:
EPD esperado vs resultado real

Variables:
- Nacidos vivos reales
- Mortalidad
- GMD real
- FCR real

Uso:
- Ajuste heredabilidades
- Mejora índice económico
- Aprendizaje continuo del motor