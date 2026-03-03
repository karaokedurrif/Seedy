# 🌱 Seedy — IA Técnica para NeoFarm

**Seedy** es el sistema de inteligencia artificial que asiste a la plataforma [NeoFarm](https://hub.vacasdata.com) (ganadería de precisión). Sistema multi-agente con 6 modelos especializados, RAG con 6 colecciones de conocimiento, y un modelo fine-tuned (Qwen2.5-7B + LoRA).

> Seedy responde preguntas técnicas sobre IoT ganadero, nutrición animal, genética aplicada, normativa SIGE, Digital Twins y economía ganadera.

---

## 📋 Contenido del repositorio

| Archivo/Carpeta | Descripción |
|---|---|
| `build_v4.py` | Script de generación del dataset SFT v4 (limpieza, dedup, enriquecimiento, nuevos ejemplos) |
| `seedy_dataset_sft_v3_plus60.jsonl` | Dataset SFT v3 (base) |
| `seedy_dataset_sft_v4.jsonl` | Dataset SFT v4 (150 ejemplos, usado para fine-tune) |
| `conocimientos/` | 6 colecciones de conocimiento RAG (IoT, Nutrición, Genética, Estrategia, Digital Twins, Normativa) |
| `.github/SEEDY_COPILOT_INSTRUCTIONS.md` | Instrucciones completas del proyecto para Copilot/IA |
| `Arquitectura recomendada LLM.txt` | Documento de arquitectura LLM |

## 🧠 Dominios de conocimiento

1. **PorciData — IoT & Hardware**: BOM 7+1 capas (~1.420 EUR/nave), sensores, firmware ESP32
2. **Nutrición & Formulación**: Butirato sódico, enzimas NSP, NRC 2012, solver LP HiGHS, lonjas
3. **NeoFarm Genética**: Consanguinidad Wright, EPDs, motor FarmMatch, razas autóctonas
4. **Estrategia & Competencia**: Análisis competitivo, posicionamiento, Fancom vs Nedap
5. **Digital Twins & IoT**: Twins porcino/vacuno, Mioty vs LoRa, playbooks, centinelas
6. **Normativa & SIGE**: RD 306/2020 (11 planes SIGE), ECOGAN 8 pasos, RD 1135/2002

## 🔧 Fine-tune

- **Plataforma**: Together.ai
- **Job ID**: `ft-bc10fc32-2235`
- **Base**: Qwen2.5-7B-Instruct
- **Tipo**: LoRA (~75 MB adapter)
- **Dataset**: 150 ejemplos SFT en español
- **Modelo local**: GGUF Q8_0 (7.6 GB) — desplegado en Ollama como `seedy:q8`

## 🏗️ Stack desplegado

- **Ollama** — modelos locales (seedy:q8, qwen2.5:7b, mxbai-embed-large)
- **Open WebUI** — interfaz web para los 6 modelos Seedy
- **Hardware**: MSI Vector 16 HX (RTX 5080 16GB, 64GB RAM, Ubuntu 24.04)

## 📐 Arquitectura objetivo

```
Usuario (Open WebUI / hub.vacasdata.com / App Móvil)
    ↓
Seedy Backend (FastAPI) → Clasificación → RAG (Qdrant) → Rerank → LLM (Together.ai / Ollama fallback)
    ↓
Digital Twin Engine (InfluxDB + MQTT + Node-RED + Grafana)
```

## 📄 Licencia

Proyecto privado — NeoFarm / VacasData.
