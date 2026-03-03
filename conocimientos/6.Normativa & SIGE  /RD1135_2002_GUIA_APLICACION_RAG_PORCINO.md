---
document_type: normativa_aplicacion
norma_principal: RD_1135_2002
sector: porcino
ambito: bienestar_animal
aplicable_a: [intensivo, extensivo_con_instalaciones_permanentes]
relacion_directivas: [2008/120/CE, 2001/88/CE, 2001/93/CE]
tags: [bienestar, superficies, gestacion_grupo, suelos, mutilaciones, destete]
version_guia: ANPROGAPOR_2012
---

# RD 1135/2002 — PROTECCIÓN DE LOS CERDOS
## VERSIÓN ESTRUCTURADA PARA RAG

---

# BLOQUE 1 — OBJETO DE LA NORMA

[META]
tipo: alcance

Establece las normas mínimas para la protección de:
- Cerdos de cría
- Cerdos de engorde
- Reproductoras
- Verracos

Aplicable también a porcino extensivo con excepciones específicas :contentReference[oaicite:1]{index=1}

---

# BLOQUE 2 — DEFINICIONES CLAVE

[META]
tipo: definiciones_normativas

- Cerda joven = hembra tras pubertad y antes del primer parto
- Cerda = hembra tras primer parto
- Cerdo de producción = >10 semanas hasta sacrificio
- Cochinillo destetado = hasta 10 semanas
- Verraco = macho reproductor

Importante para automatizar validaciones por categoría.

---

# BLOQUE 3 — SUPERFICIE DE SUELO LIBRE (CEBO)

[META]
tipo: superficie_minima
aplica_a: lechones_y_cebo

| Peso vivo | m² mínimos |
|------------|------------|
| Hasta 10 kg | 0,15 |
| 10–20 kg | 0,20 |
| 20–30 kg | 0,30 |
| 30–50 kg | 0,40 |
| 50–85 kg | 0,55 |
| 85–110 kg | 0,65 |
| >110 kg | 1,00 |

Fuente tabla oficial página 14 :contentReference[oaicite:2]{index=2}

---

# BLOQUE 4 — SUPERFICIE CERDAS EN GRUPO (GESTACIÓN)

[META]
tipo: superficie_reproductoras
clave: tamaño_grupo

| Tamaño grupo | Cerda (m²) | Cerda joven (m²) |
|---------------|------------|------------------|
| 2–5 animales | 2,475 | 1,804 |
| 6–39 animales | 2,250 | 1,640 |
| ≥40 animales | 2,025 | 1,476 |

Tabla oficial página 14 :contentReference[oaicite:3]{index=3}

---

# BLOQUE 5 — GESTACIÓN EN GRUPOS

[META]
tipo: manejo_reproductivo

Obligatorio:
- Desde 4 semanas post-cubrición
- Hasta 7 días antes del parto :contentReference[oaicite:4]{index=4}

Duración técnica gestación: 17 semanas

Excepciones:
- <10 cerdas pueden alojarse individualmente
- Animales agresivos/enfermos pueden aislarse

---

# BLOQUE 6 — DIMENSIONES RECINTOS GESTACIÓN

[META]
tipo: requisitos_instalacion

- Lados recinto >2,8 m
- Si grupo 2–5 animales → >2,4 m :contentReference[oaicite:5]{index=5}

---

# BLOQUE 7 — SUELOS CERDAS GESTANTES

[META]
tipo: revestimiento_suelo

Requisitos:
- Parte suelo continuo compacto <15% drenaje
- Mínimo:
  - 1,3 m²/cerda
  - 0,95 m²/cerda joven :contentReference[oaicite:6]{index=6}

Si emparrillado hormigón:
- Vigueta ≥80 mm
- Abertura ≤20 mm

---

# BLOQUE 8 — SUELOS LECHONES Y CEBO

[META]
tipo: emparrillado

| Animal | Vigueta mín | Abertura máx |
|---------|-------------|--------------|
| Lechón | 50 mm | 11 mm |
| Cochinillo | 50 mm | 14 mm |
| Producción | 80 mm | 18 mm |

Con tolerancia UNE ±2 mm / ±3 mm :contentReference[oaicite:7]{index=7}

---

# BLOQUE 9 — MATERIAL MANIPULABLE

[META]
tipo: enriquecimiento

Obligatorio acceso a:
- Paja
- Heno
- Madera
- Serrín
- Turba
- Compost

Para prevenir raboteo :contentReference[oaicite:8]{index=8}

---

# BLOQUE 10 — MUTILACIONES

[META]
tipo: prohibiciones

Prohibido:
- Procedimientos que provoquen lesiones

Permitido:
- Reducción dientes (<7 días)
- Raboteo parcial
- Castración <7 días
- Anillado hocico en extensivo

Si >7 días → anestesia + analgesia veterinaria :contentReference[oaicite:9]{index=9}

---

# BLOQUE 11 — DESTETE

[META]
tipo: edad_destete

- Edad mínima: 28 días
- Puede adelantarse a 21 días si:
  - Problema sanitario
  - Instalaciones adecuadas :contentReference[oaicite:10]{index=10}

---

# BLOQUE 12 — CONDICIONES GENERALES

[META]
tipo: ambiente

- Ruido <85 dB
- Luz ≥40 lux durante 8h
- Zona descanso suficiente
- Protección antiaplastamiento en partos :contentReference[oaicite:11]{index=11}

---

# BLOQUE 13 — VERRACOS

[META]
tipo: requisitos_especificos

- 6 m² mínimos
- 10 m² si se usa para cubrición :contentReference[oaicite:12]{index=12}

---

# BLOQUE 14 — CÁLCULO DISTRIBUCIÓN GRANJA

[META]
tipo: modelizacion_instalaciones

Ejemplo granja 150 partos:
- 150 partos
- 258 gestación jaulas
- 360 gestación grupos
Total: 768 reproductoras :contentReference[oaicite:13]{index=13}

Útil para:
- Digital Twin reproductivo
- Simulación capacidad

---

# BLOQUE 15 — REPOSICIÓN

[META]
tipo: estructura_censo

Estructura estándar:
- 20% cerdas jóvenes
- 80% cerdas adultas :contentReference[oaicite:14]{index=14}

Clave para:
- Cálculo espacio grupo mixto
- Predicción necesidades futuras

---

# FIN DOCUMENTO