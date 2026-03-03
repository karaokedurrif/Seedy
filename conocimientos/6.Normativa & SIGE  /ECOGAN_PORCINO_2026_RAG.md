---
document_type: normativa_tecnica
sistema: ECOGAN
sector: porcino_intensivo
version_manual: febrero_2026
organismo: MAPA
normativa_relacionada: [Decisión UE 2017/302, RD 306/2020, RDL 1/2016]
tags: [ECOGAN, emisiones, MTD, purines, AAI, declaración, REGA]
---

# MANUAL ECOGAN PORCINO — VERSIÓN RAG OPTIMIZADA

---

# BLOQUE 1 — QUÉ ES ECOGAN

[META]
tipo: sistema_declarativo
obligatoriedad: declaración_emisiones

ECOGAN es el sistema informatizado del MAPA para:
- Declaración de emisiones en explotaciones porcinas
- Registro de MTDs aplicadas
- Cálculo automático de emisiones
- Comunicación a CCAA y MAPA

Manual perfil ganadero (Febrero 2026).

---

# BLOQUE 2 — ESTRUCTURA DEL SISTEMA (FLUJO POR PASOS)

[META]
tipo: estructura_operativa
uso: navegación_RAG

ECOGAN se organiza en 8 pasos principales:

1. Datos de granja :contentReference[oaicite:7]{index=7}
2. Alojamientos :contentReference[oaicite:8]{index=8}
3. Sistemas de almacenamiento exterior :contentReference[oaicite:9]{index=9}
4. Gestión de alojamientos (energía, agua)
5. Uso agrícola
6. Consumos y aguas residuales
7. Resultados
8. Autorización Ambiental Integrada

---

# BLOQUE 3 — PASO 1: DATOS DE GRANJA

[META]
categoria: datos_base
clave: REGA

Incluye:
- Identificación explotación
- Plazas
- Sistema de gestión ambiental
- Plan formación
- Gestión cadáveres
- AAI :contentReference[oaicite:10]{index=10}

---

# BLOQUE 4 — PASO 2: ALOJAMIENTOS

[META]
categoria: instalaciones
impacto: emisiones

Se define:
- Tipo de sistema productivo
- Categoría animal
- Tipo de suelo
- Sistema de almacenamiento interior
- Control emisiones NH3, polvo, olores :contentReference[oaicite:11]{index=11}

---

# BLOQUE 5 — CATEGORÍAS ESPECIALES

[META]
categoria: categorias_productivas

## Recría

Tratamiento como cebo (18–20 kg entrada / 100–130 kg salida) :contentReference[oaicite:12]{index=12}

## Wean to finish

Debe declararse como CEBO completo (6 kg a 110 kg) :contentReference[oaicite:13]{index=13}

Evita duplicación de ciclos productivos.

---

# BLOQUE 6 — PASO 3: ALMACENAMIENTO EXTERIOR

[META]
categoria: purines
impacto: NH3

Se declara:
- Tipo almacenamiento
- Distribución porcentual (100% obligatorio) :contentReference[oaicite:14]{index=14}
- Técnicas aplicadas

---

# BLOQUE 7 — APLICACIÓN A CAMPO

[META]
categoria: uso_agricola
clave: tecnicas_MTD

Debe indicarse:
- Nº técnicas aplicadas
- Porcentaje uso
- Enterrado <12h
- Programa abonado :contentReference[oaicite:15]{index=15}

Colores:
- Naranja = incompleto
- Blanco = completo :contentReference[oaicite:16]{index=16}

---

# BLOQUE 8 — ENERGÍA Y AGUA

[META]
categoria: consumos
impacto: eficiencia

Se declara por alojamiento:
- Energía :contentReference[oaicite:17]{index=17}
- Agua :contentReference[oaicite:18]{index=18}

---

# BLOQUE 9 — INFORMES

[META]
categoria: verificacion

## Informe Ganadero
Listado completo preguntas/respuestas :contentReference[oaicite:19]{index=19}

## Informe MTDs
Incluye:
- Justificante registro
- Listado técnicas aplicadas
- % reducción emisiones :contentReference[oaicite:20]{index=20}

Código implementación:
- SI
- NO
- NO APLICABLE :contentReference[oaicite:21]{index=21}

---

# BLOQUE 10 — MTDs (MEJORES TÉCNICAS DISPONIBLES)

[META]
categoria: MTD
normativa: Decisión UE 2017/302

Agrupadas por fase productiva:
- Alimentación
- Alojamiento
- Almacenamiento
- Aplicación a campo :contentReference[oaicite:22]{index=22}

Incluye porcentaje reducción NH3.

---

# BLOQUE 11 — RESULTADOS Y COMUNICACIÓN

[META]
categoria: declaracion

Tras validar:
- Se comunica a CCAA
- CCAA notifica a MAPA
- Declaración bloqueada hasta siguiente periodo :contentReference[oaicite:23]{index=23}

Asociada siempre al código REGA :contentReference[oaicite:24]{index=24}

---

# BLOQUE 12 — AUTORIZACIÓN AMBIENTAL INTEGRADA (AAI)

[META]
categoria: AAI
normativa: RDL_1_2016

AAI obligatoria para explotaciones afectadas :contentReference[oaicite:25]{index=25}

Incluye:
- Condicionado ambiental
- Control integrado contaminación

---

# BLOQUE 13 — PERFILES DE USUARIO

[META]
categoria: roles

Perfiles:
- Ganadero
- Representante legal
- Autorizado :contentReference[oaicite:26]{index=26}

Funciones:
- Declaración
- Simulador
- Comunicación multi-CCAA

---

# BLOQUE 14 — REQUISITOS INFORMÁTICOS

[META]
categoria: requisitos_tecnicos

Sistemas:
- Windows 8.1 / 10 / 11 :contentReference[oaicite:27]{index=27}
- Chrome / Firefox / Edge

---

# FIN DOCUMENTO