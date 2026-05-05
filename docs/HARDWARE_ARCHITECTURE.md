# Arquitectura Hardware Seedy v4.7

**Fecha:** 5 mayo 2026  
**Propósito:** Aclaración de qué hardware corre qué servicios

---

## 🖥️ Máquinas en el Stack

### 1. DGX Spark (Lenovo) — GPU Server

**IP:** 192.168.20.57 (WiFi), 10.10.10.200 (Ethernet cámaras)  
**GPU:** NVIDIA GB10 (Blackwell, compute capability 12.1)  
**RAM:** 128 GB unificada ARM64  
**OS:** Ubuntu 24.04 LTS  
**Driver:** NVIDIA 580.142 Open Kernel Module

**Servicios que corre:**
- ✅ **Ollama** (puerto 11434) — LLM para RAG pipeline Seedy 24/7
  - qwen2.5:7b (4.7 GB) — rewriter, classifiers
  - qwen2.5:72b (47 GB) — análisis batch Celery workers
  - seedy:v16 (9 GB) — critic gate, modos /local y /eco
  - mxbai-embed-large (0.7 GB) — embeddings RAG
- ✅ **vLLM** (puerto 8001) — Coder engine v4.7 on-demand
  - Qwen2.5-Coder-32B-Instruct-AWQ (22 GB)
  - PagedAttention 8 sesiones concurrentes
  - OpenAI-compatible API
- ✅ **17 contenedores Docker** (stack Seedy completo)
  - Backend FastAPI, Qdrant, Redis, Celery, go2rtc, etc.

**Memoria GPU worst-case:**
- Ollama: ~60 GB (qwen2.5:72b + KV cache + embeddings)
- vLLM: ~46 GB (Qwen2.5-Coder-32B-AWQ + KV cache) cuando activo
- **Total:** 106/128 GB (82% uso) cuando ambos engines activos

**Nota crítica:** Esta máquina es el "cerebro" de Seedy. Todo el procesamiento LLM ocurre aquí.

---

### 2. MSI Vector 16 HX — Workstation Local (NO en producción)

**GPU:** NVIDIA RTX 5080 (16 GB VRAM, Ada Lovelace)  
**RAM:** 64 GB DDR5  
**OS:** Ubuntu 24.04 LTS  
**Driver:** NVIDIA 580.xxx

**Servicios que corre:**
- ❌ **Ningún LLM en producción**
- ✅ Desarrollo local / testing
- ✅ Continue.dev (VS Code) — cliente que consume vLLM del DGX
- ✅ Git repository local (push/pull a DGX y GitHub)

**Nota:** Esta es la máquina del desarrollador. La RTX 5080 aquí NO participa en el stack de producción Seedy.

---

### 3. Mini PC Zigbee (Karaoke) — Sensor Gateway

**IP:** 192.168.20.54  
**Hardware:** Mini PC Linux Mint 22.2  
**Servicios:**
- ✅ Zigbee2MQTT (Docker :8080) — 7 sensores Zigbee
- ✅ Openclaw — SOC monitoring (cliente vLLM 32B para análisis)

---

### 4. Jetson Orin Nano 8GB — Edge Vision (Futuro, bloqueado hasta cable HDMI)

**Status:** Hardware conectado, esperando DisplayPort/HDMI para setup  
**GPU:** 67 TOPS (JetPack 6.2 Super Mode)  
**Función planeada:** 
- YOLO inference local
- Tracking aves
- Event triggers
- Redis queue → DGX backend

**No operativo actualmente.**

---

## 📊 Diagrama Arquitectura Simplificado

```
┌──────────────────────────────────────────────────┐
│  MSI VECTOR 16 HX (Workstation local)            │
│  ├─ RTX 5080 (16GB) — NO en producción          │
│  ├─ Continue.dev → consume vLLM remoto          │
│  └─ Git repo local                               │
└──────────────────────────────────────────────────┘
                       ▲
                       │ API calls HTTP
                       │
┌──────────────────────────────────────────────────┐
│  DGX SPARK LENOVO (GPU Server) ⬅ CEREBRO        │
│                                                   │
│  ┌─────────────────────────────────────────┐    │
│  │ GPU NVIDIA GB10 (128GB unified RAM)     │    │
│  │                                          │    │
│  │  ┌──────────────────────────────────┐   │    │
│  │  │ Ollama :11434 (24/7)             │   │    │
│  │  │ ├─ qwen2.5:7b (4.7 GB)          │   │    │
│  │  │ ├─ qwen2.5:72b (47 GB)          │   │    │
│  │  │ └─ seedy:v16 (9 GB)             │   │    │
│  │  └──────────────────────────────────┘   │    │
│  │                                          │    │
│  │  ┌──────────────────────────────────┐   │    │
│  │  │ vLLM :8001 (on-demand) v4.7      │   │    │
│  │  │ └─ qwen2.5-coder-32b-awq (22GB) │   │    │
│  │  │    ├─ PagedAttention (8 conc)   │   │    │
│  │  │    └─ OpenAI-compatible API     │   │    │
│  │  └──────────────────────────────────┘   │    │
│  │                                          │    │
│  │  Worst-case: 106/128 GB (82%)           │    │
│  └─────────────────────────────────────────┘    │
│                                                   │
│  ├─ Backend FastAPI :8000                        │
│  ├─ Qdrant :6333 (11 colecciones RAG)            │
│  ├─ Redis :6379 (Celery broker)                  │
│  ├─ Celery workers (behavior ML, reports)        │
│  └─ 17 contenedores Docker total                 │
└──────────────────────────────────────────────────┘
                       ▲
                       │ vLLM API HTTP
                       │
┌──────────────────────────────────────────────────┐
│  MINI PC ZIGBEE (192.168.20.54)                  │
│  ├─ Zigbee2MQTT (sensor gateway)                 │
│  └─ Openclaw (SOC) → vLLM 32B                    │
└──────────────────────────────────────────────────┘
```

---

## ⚠️ Confusión Común: "RTX 5080 GB10"

**ERROR:** Decir "RTX 5080 GB10" mezclando ambas máquinas.

**CORRECTO:**
- **GPU en producción:** NVIDIA **GB10** (en DGX Spark Lenovo)
- **GPU en workstation:** NVIDIA **RTX 5080** (en MSI Vector, NO en producción)

**NO existe** una "RTX 5080 GB10". Son dos GPUs diferentes en dos máquinas diferentes:
- GB10 = Server (Blackwell, ARM64, 128GB unified)
- RTX 5080 = Workstation (Ada Lovelace, x86-64, 16GB VRAM)

---

## 💾 Memoria GPU Breakdown (DGX Spark GB10)

### Escenario 1: Solo Ollama (actual pre-v4.7)
- **qwen2.5:72b loaded:** 47 GB modelo + 10 GB KV cache = 57 GB
- **qwen2.5:7b loaded:** 4.7 GB modelo + 2 GB KV cache = 6.7 GB
- **seedy:v16 loaded:** 9 GB modelo + 2 GB KV cache = 11 GB
- **mxbai-embed-large:** 0.7 GB
- **Total:** ~75/128 GB (59%)

### Escenario 2: Ollama + vLLM ambos activos (v4.7 worst-case)
- **Ollama base:** 60 GB (72B + embeddings + KV caches)
- **vLLM Qwen2.5-Coder-32B-AWQ:** 22 GB modelo + 24 GB KV cache (8 sessions PagedAttention) = 46 GB
- **Total:** 106/128 GB (82%)

### Escenario 3: Solo Ollama con vLLM idle
- **Ollama:** 60 GB
- **vLLM:** 0 GB (no loaded)
- **Total:** 60/128 GB (47%)

**Arquitectura unificada GB10:** La memoria es compartida entre CPU y GPU (128 GB total pool), por eso `nvidia-smi` muestra "N/A" en memoria GPU. Esto es **normal y esperado** en arquitectura ARM64 con unified memory.

---

## 🔀 Flujo de Datos Típico

### Chat usuario en Open WebUI (seedy.neofarm.io)

```
User query → Open WebUI (MSI) → Backend API (DGX) → llm_router
  → classify_category (DGX Ollama qwen2.5:7b, <0.3s, $0)
  → classify_temporality (DGX Ollama qwen2.5:7b, <0.3s, $0)
  → query_rewriter (DGX Ollama qwen2.5:7b, <0.6s, $0)
  → Qdrant search (DGX :6333)
  → Reranker (DGX)
  → LLM generation (Together.ai qwen3-235b, ~20s, $0.003)
  → Critic gate (DGX Ollama seedy:v16, <1s, $0)
  → Response → Open WebUI
```

**Ollama usage:** 4 pasos (45% del pipeline)  
**Together.ai usage:** 1 paso (55% coste, pero solo generation)  
**Ahorro:** -30% coste vs antes (todo en Together.ai)

### Openclaw SOC analysis (mini PC)

```
Sensor MQTT → Openclaw (mini PC)
  → Consolidate telemetry → Analyze pattern
  → HTTP POST → vLLM (DGX :8001) with qwen2.5-coder-32b
  → Response: {severity, description, recommendation}
  → Alert/Log
```

**vLLM usage:** On-demand cuando Openclaw detecta patrón  
**Coste:** $0 (local)  
**Calidad:** 6/10 (qwen2.5:7b) → 8.5/10 (qwen2.5-coder-32b)

### Continue.dev coding (MSI workstation)

```
VS Code (MSI) → Continue.dev extension
  → Tab autocomplete request → HTTP POST → vLLM (DGX :8001)
  → Qwen2.5-Coder-32B-AWQ inference → Response (15-22 tok/s)
  → Autocomplete rendered in VS Code
```

**vLLM usage:** On-demand when typing código  
**Latency:** ~1-2s para 20-40 tokens  
**Coste:** $0 vs $0.10/M tokens Together.ai

---

## 📈 Evolución Arquitectura

| Fase | Época | GPU en Producción | Descripción |
|------|-------|-------------------|-------------|
| **v4.0-4.5** | Feb-Abr 2026 | Ninguna (Together.ai 100%) | Todo en cloud, $207/mes |
| **v4.6** | Mayo 2026 | GB10 con Ollama | Hibridación pasos pequeños, $120/mes (-42%) |
| **v4.7** | Mayo 2026 | GB10 con Ollama + vLLM | Dual-engine coding + RAG, $85-100/mes estimado (-50%) |

---

**Última actualización:** 5 mayo 2026 18:30 CEST  
**Autor:** GitHub Copilot (corrección tras aclaración del usuario)  
**Propósito:** Documentar arquitectura hardware real sin ambigüedades
