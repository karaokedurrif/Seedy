# Análisis de Problemas de Calidad en Chat Export

**Fecha:** 5 mayo 2026  
**Archivo analizado:** `/home/davidia/Descargas/chat-export-1777933127461.json`  
**Problema reportado:** Respuestas con datos inventados e informes falsos

---

## 🔴 PROBLEMAS DETECTADOS

### 1. **INVENCIÓN DE PILOTO INEXISTENTE**

**Respuesta de Seedy dice:**
> "Piloto de NeoFarm con 2,000 pollitos en El Gallinero del Palacio (Segovia)"  
> "Periodo monitoreado: 0-35 días (5 semanas)"  
> "Informe piloto 'El Gallinero del Palacio' (NeoFarm, 2023)"

**La realidad:**
- ✅ "El Gallinero del Palacio" SÍ existe → es tu gallinero en Palacio (Segovia)
- ❌ Tiene 25 gallinas ADULTAS (no 2,000 pollitos)
- ❌ NO existe ningún piloto de pollitos documentado
- ❌ El "Informe piloto (NeoFarm, 2023)" NO EXISTE en la base de conocimiento

**Búsqueda en conocimientos/:**
```bash
grep -r "piloto.*2000.*pollitos" conocimientos/  # 0 resultados
grep -r "2,000 pollitos" conocimientos/           # 0 resultados
```

### 2. **MÉTRICAS INVENTADAS**

**Respuesta dice:**
- "Dahua IPC-HFW3849T1 logró 94% precisión en detección de conductas anómalas"
- "Alertas tempranas redujeron mortalidad en 18%"
- "TP-Link VIGI C340 detectó pollitos de 1 semana (peso ~35g) con confianza YOLO >0.85"

**La realidad:**
- ❌ Ninguna de estas métricas específicas está en conocimientos/
- ❌ No existe ningún estudio de mortalidad con cifras 18%
- ❌ Las pruebas actuales son con gallinas adultas, no pollitos

### 3. **FUENTES FALSAS**

**Respuesta cita:**
1. "Especificaciones técnicas Dahua WizSense (modelos 2024)" → ⚠️ Genérico
2. "Informe piloto 'El Gallinero del Palacio' (NeoFarm, 2023)" → ❌ **NO EXISTE**
3. "Benchmark YOLOv8 en avicultura (Ultralytics, 2024)" → ⚠️ Genérico

---

## 🔍 CAUSA ROOT

### **Modo `/think` usa DeepSeek-R1 sin fine-tuning de Seedy**

El flujo actual es:

```
Usuario: "/think Qué cámaras..."
  ↓
chat_modes.py: detecta mode="think"
  ↓
llm_modes.py: usa POLICIES["generation_think"]
  ↓
Policy "generation_think":
  primary: "together:deepseek-r1"  ← MODELO GENÉRICO
  fallback: ["together:qwen3-235b-tput", "ollama:seedy-v16"]
  ↓
DeepSeek-R1 recibe:
  - Query original
  - Chunks de RAG (probablemente sobre cámaras Dahua/VIGI)
  - NO tiene fine-tuning de Seedy
  ↓
DeepSeek-R1 hace pattern matching y rellena vacíos:
  - Ve "El Gallinero del Palacio" en RAG
  - Ve specs de cámaras Dahua/VIGI
  - INVENTA un "piloto" porque suena coherente
  - INVENTA métricas (94%, 18%) porque necesita cifras
  - CITA un "Informe NeoFarm 2023" porque parece legítimo
  ↓
critic.py: evaluate_technical_accuracy()
  ↓
TECHNICAL_CRITIC_SYSTEM prompt dice:
  "NO BLOQUEAR por:
   - Hechos que NO están en la evidencia pero son plausibles
   - Conocimiento técnico del modelo
   - Datos técnicos específicos del dominio"
  
  "RECUERDA: El modelo principal es EXPERTO en su dominio.
   Si da un dato técnico que no aparece en la evidencia
   pero es plausible, eso es conocimiento propio, NO invención."
  ↓
Critic: PASS ✅ (datos parecen plausibles)
  ↓
Usuario recibe respuesta con ALUCINACIONES
```

### **Problema de diseño:**

El TECHNICAL_CRITIC está calibrado para **confiar** en `ollama:seedy-v16` (que SÍ tiene fine-tuning), pero el modo `/think` usa `together:deepseek-r1` (genérico).

**GAP DE CONFIABILIDAD:**
- Critic diseñado para: seedy:v16 (fine-tuned, conocimiento propio confiable)
- Realmente evaluando: deepseek-r1 (genérico, rellena vacíos con inventos)

---

## ✅ SOLUCIONES PROPUESTAS

### **SOLUCIÓN 1 — INMEDIATA (1-2h): Critic más estricto para citas**

Modificar `backend/services/critic.py` → `TECHNICAL_CRITIC_SYSTEM`:

```python
TECHNICAL_CRITIC_SYSTEM = (
    "Eres un evaluador de fidelidad factual para Seedy...\n\n"
    # ... prompt existente ...
    "\n\n"
    "NUEVAS REGLAS CRÍTICAS PARA BLOQUEAR:\n"
    "4. CITA FALSA DE DOCUMENTO: La respuesta cita un 'Informe X', 'Estudio Y', "
    "'Piloto Z', 'Benchmark W' específico que NO aparece en la evidencia. "
    "Ejemplo: 'Informe piloto El Gallinero del Palacio (NeoFarm, 2023)' pero "
    "la evidencia no contiene ese documento. BLOQUEAR con tag 'fuente_falsa'.\n"
    "5. MÉTRICAS ESPECÍFICAS SIN EVIDENCIA: La respuesta da cifras muy precisas "
    "(XX%, YY tok/s, ZZ días) sobre resultados de un piloto/experimento específico, "
    "pero la evidencia no contiene esos números. Conocimiento técnico general OK "
    "(ej: 'gallinas ponen ~280 huevos/año'), pero resultados de un estudio concreto "
    "inventados = BLOQUEAR con tag 'metricas_falsas'.\n"
    "6. PILOTOS/PRUEBAS INVENTADOS: La respuesta describe un piloto/prueba/despliegue "
    "real específico ('piloto con 2,000 pollitos en Segovia', 'estudio de 6 meses') "
    "que NO aparece en la evidencia. BLOQUEAR con tag 'piloto_falso'.\n"
)
```

**Impacto:**
- ✅ Detecta las alucinaciones del chat analizado
- ✅ Funciona para todos los modos (/think, /default, /deep)
- ⚠️ Puede generar más false positives (bloqueos incorrectos) al inicio

**Test necesario:** 30 queries de regresión para validar que no sobre-bloquea.

---

### **SOLUCIÓN 2 — CORTO PLAZO (30min): Cambiar primary model de /think**

Modificar `backend/services/llm_router/policy.py`:

```python
"generation_think": StepPolicy(
    name="generation_think",
    # ANTES: primary="together:deepseek-r1",  # Genérico, alucina
    primary="ollama:seedy-v16",              # Fine-tuned, más confiable
    fallback=["together:deepseek-r1", "together:qwen3-235b-tput"],
    max_latency_s=60.0,
    requires_user=True,
),
```

**Pros:**
- ✅ seedy:v16 tiene fine-tuning específico de Seedy
- ✅ Menos propenso a inventar datos del dominio
- ✅ El critic está calibrado para confiar en seedy:v16

**Contras:**
- ⚠️ seedy:v16 (14B) es menos potente que DeepSeek-R1 (670B) para reasoning complejo
- ⚠️ Latencia local ~13s vs 24s cloud (pero dentro del SLA 60s)

**Alternativa:** Cambiar a `together:qwen3-235b-tput` (cloud, 235B, confiable):
```python
primary="together:qwen3-235b-tput",  # 235B Together.ai, mejor que R1 para dominio
fallback=["ollama:seedy-v16"],
```

---

### **SOLUCIÓN 3 — MEDIO PLAZO (2-3h): System prompt más restrictivo**

Añadir directiva explícita en `backend/models/prompts.py` → `SYSTEM_PROMPT`:

```python
SYSTEM_PROMPT = (
    "Eres Seedy, el asistente de inteligencia artificial de NeoFarm...\n\n"
    # ... contenido existente ...
    "\n\n"
    "═══ REGLAS DE CITACIÓN Y DATOS ═══\n"
    "1. SOLO cita documentos/informes/pilotos que estén EXPLÍCITAMENTE en el contexto proporcionado.\n"
    "2. Si el contexto menciona un 'piloto' o 'estudio', usa ESE nombre exacto, no inventes otro.\n"
    "3. Si no tienes datos específicos de un piloto/experimento, di 'no dispongo de datos concretos', "
    "NO inventes cifras (XX%, YY días, etc.).\n"
    "4. Métricas técnicas GENÉRICAS del dominio OK (ej: 'gallinas ponen 250-300 huevos/año'), "
    "pero resultados de estudios ESPECÍFICOS solo si están en la evidencia.\n"
    "5. Si necesitas extrapolar, usa lenguaje condicional: 'podría', 'típicamente', 'se estima', "
    "NO lenguaje asertivo: 'logró', 'en nuestro piloto', 'según el informe'.\n\n"
    "Si el contexto no contiene la información solicitada, admítelo honestamente.\n"
    "NO rellenes vacíos con inventos plausibles."
)
```

**Impacto:**
- ✅ Previene alucinaciones en origen (prompt engineering)
- ✅ Funciona para todos los modos y modelos
- ⚠️ Puede hacer respuestas más conservadoras/incompletas

---

### **SOLUCIÓN 4 — LARGO PLAZO (8-12h): Fact-checking contra Qdrant**

Implementar verificación post-generación:

```python
# backend/services/fact_checker.py (NUEVO)
async def verify_citations(
    answer: str,
    context_chunks: list[dict],
) -> dict:
    """
    Extrae citas de la respuesta (informes, pilotos, estudios)
    y verifica si existen en la evidencia.
    
    Returns:
        {
            "verified": bool,
            "suspicious_citations": [
                {"text": "Informe piloto X", "found": False},
                ...
            ]
        }
    """
    # 1. Regex para detectar citas formales
    citation_patterns = [
        r'"([^"]+)"',                           # Entre comillas
        r'Informe ([A-Z][^.,]+)',               # Informe X
        r'Piloto ([A-Z][^.,]+)',                # Piloto Y
        r'Estudio ([A-Z][^.,]+)',               # Estudio Z
        r'Benchmark ([A-Z][^.,]+)',             # Benchmark W
        r'\(([A-Za-z0-9\s]+), \d{4}\)',        # (Autor/Org, 2024)
    ]
    
    # 2. Extraer candidatos
    # 3. Buscar en context_chunks
    # 4. Si no encuentra → "suspicious"
    # 5. Si >2 suspicious → BLOCK
```

Integrar en `chat.py` DESPUÉS del critic:
```python
# Verificar citas
fact_check = await verify_citations(answer, context_chunks)
if not fact_check["verified"]:
    logger.warning(f"[FactCheck] Citas sospechosas: {fact_check['suspicious_citations']}")
    answer = BLOCKED_FALLBACK
```

**Pros:**
- ✅ Verificación automática robusta
- ✅ Funciona para cualquier modelo

**Contras:**
- ⚠️ Complejidad alta (regex + matching difuso)
- ⚠️ Puede generar false positives (bloqueos de citas legítimas de conocimiento propio)

---

## 📊 PRIORIZACIÓN

| Solución | Esfuerzo | Impacto | Riesgo | Prioridad |
|----------|----------|---------|--------|-----------|
| **1. Critic más estricto** | 1-2h | ⭐⭐⭐⭐ Alto | ⚠️ Medio (false positives) | **🔥 1** |
| **2a. /think → seedy-v16** | 30min | ⭐⭐⭐ Medio-Alto | ⚠️ Bajo | **🔥 2** |
| **2b. /think → qwen3-235b** | 30min | ⭐⭐⭐⭐ Alto | ⚠️ Bajo | **🔥 2** |
| **3. System prompt restrictivo** | 2-3h | ⭐⭐⭐ Medio | ⚠️ Bajo | **3** |
| **4. Fact-checker Qdrant** | 8-12h | ⭐⭐⭐⭐⭐ Muy Alto | ⚠️ Alto | **4** (largo plazo) |

---

## 🎯 PLAN DE ACCIÓN RECOMENDADO

### **Fase Inmediata (hoy):**

1. ✅ Cambiar primary de `/think` a `ollama:seedy-v16` o `together:qwen3-235b-tput`
   - Tiempo: 5min código + 10min test
   - Commit: "Fix /think hallucinations: switch from deepseek-r1 to seedy-v16"

2. ✅ Mejorar TECHNICAL_CRITIC_SYSTEM con reglas de citas/métricas/pilotos
   - Tiempo: 1h implementación + 1h tests de regresión
   - Commit: "Critic v2: detect false citations, fake metrics, invented pilots"

### **Fase Corto Plazo (mañana):**

3. ✅ Añadir reglas de citación al SYSTEM_PROMPT
   - Tiempo: 2h implementación + 1h validación
   - Commit: "System prompt v2: strict citation and data grounding rules"

4. ✅ Tests de regresión ampliados
   - 50 queries cubriendo casos edge: citas, métricas, pilotos
   - Target: 0 false citations, <5% false positives en critic

### **Fase Largo Plazo (opcional):**

5. ⏸️ Fact-checker contra Qdrant
   - Solo si Soluciones 1-3 no son suficientes
   - Evaluar después de 1 semana en producción

---

## 📈 MÉTRICAS DE ÉXITO

| Métrica | Antes | Target |
|---------|-------|--------|
| Alucinaciones detectadas | ~0% (critic no detectaba) | <1% (llegan al usuario) |
| Critic BLOCK rate | ~2-3% | 5-8% (más estricto) |
| False positives | N/A | <5% (validar con usuario) |
| Calidad subjetiva usuario | ⭐⭐⭐ (3/5) | ⭐⭐⭐⭐⭐ (5/5) |

---

## 🔗 ARCHIVOS AFECTADOS

- `backend/services/critic.py` (TECHNICAL_CRITIC_SYSTEM)
- `backend/services/llm_router/policy.py` (generation_think primary)
- `backend/models/prompts.py` (SYSTEM_PROMPT reglas citación)
- `backend/tests/test_critic_v2.py` (NUEVO — tests de regresión)
- `backend/services/fact_checker.py` (NUEVO — opcional fase 4)

---

**Última actualización:** 5 mayo 2026 03:00 UTC  
**Analista:** IA Expert mode  
**Próxima acción:** Decidir entre Solución 2a (seedy-v16) o 2b (qwen3-235b) para /think
