# Seedy Coder v4.3 — Guía de configuración para Continue.dev

## 1. Instalar el Modelfile local

```bash
cd /home/davidia/Documentos/Seedy
ollama create seedy-coder:agritech -f ollama/seedy-coder.Modelfile
ollama run seedy-coder:agritech "// test"
```

El modelo necesita **~9 GB de VRAM** (Qwen2.5-Coder 14B Q4_K_M). La RTX 5080 lo carga entero.

---

## 2. Configurar Continue.dev

Edita `~/.continue/config.yaml` con el siguiente contenido:

```yaml
name: Seedy
version: 1.0.0
schema: v1

models:
  # Chat principal — router automático elige el mejor modelo según la tarea
  - name: Seedy Auto
    provider: openai
    apiBase: https://seedy-api.neofarm.io/v1/code
    apiKey: YOUR_SEEDY_API_KEY
    model: seedy-auto
    roles:
      - chat
      - edit
      - apply
    defaultCompletionOptions:
      temperature: 0.2
      maxTokens: 2048
    requestOptions:
      headers:
        X-Seedy-Tier: balanced
        X-Seedy-Project: ovosfera-backend

  # Autocomplete — Ollama local vía Seedy (latencia < 150 ms)
  - name: Seedy FIM
    provider: openai
    apiBase: https://seedy-api.neofarm.io/v1/code
    apiKey: YOUR_SEEDY_API_KEY
    model: seedy-fim
    useLegacyCompletionsEndpoint: true
    roles:
      - autocomplete
    autocompleteOptions:
      debounceDelay: 200
      maxPromptTokens: 1024
      onlyMyCode: true

  # Tier MAX — para decisiones de arquitectura o refactors complejos
  - name: Seedy Max
    provider: openai
    apiBase: https://seedy-api.neofarm.io/v1/code
    apiKey: YOUR_SEEDY_API_KEY
    model: seedy-max
    roles:
      - chat
    defaultCompletionOptions:
      temperature: 0.2
      maxTokens: 4096
    requestOptions:
      headers:
        X-Seedy-Tier: max
        X-Seedy-Project: ovosfera-backend

context:
  - provider: file
  - provider: code
  - provider: diff
  - provider: terminal
  - provider: codebase
```

---

## 3. Tiers disponibles

| Tier | Header | Cuándo usarlo |
|------|--------|--------------|
| `auto` | `X-Seedy-Tier: auto` | Default. Análisis dinámico por tarea |
| `local` | `X-Seedy-Tier: local` | Sin red (avión, campo) o ahorro total |
| `balanced` | `X-Seedy-Tier: balanced` | Recomendado para uso diario |
| `max` | `X-Seedy-Tier: max` | Arquitectura y refactors complejos |

---

## 4. Routing automático — ¿qué modelo elige Seedy para cada tarea?

| Tipo de tarea | Modelo elegido | Coste aproximado |
|---------------|----------------|-----------------|
| Autocomplete (FIM) | Ollama local `seedy-coder:agritech` | $0 |
| Edit inline / pregunta corta | Qwen3-Coder-Next FP8 | ~$0.001 |
| Chat con contexto | GLM-5.1 | ~$0.005 |
| Refactor multi-fichero | Qwen3-Coder-480B | ~$0.02 |
| Arquitectura / decisión | GLM-5.1 (o Claude Opus 4.7 si tier=max) | ~$0.01-$0.05 |
| Debug de stack trace | GLM-5.1 | ~$0.005 |
| Agent mode (tools) | GLM-5.1 / MiniMax M2.7 | ~$0.01 |

---

## 5. Headers extra opcionales

Puedes añadirlos en `requestOptions.headers` de tu config:

| Header | Valores | Efecto |
|--------|---------|--------|
| `X-Seedy-Force-Model` | `glm-5.1`, `qwen3-coder-next`, `qwen3-coder-480b` | Bypass del router (debug) |
| `X-Seedy-Project` | cualquier slug | Agrupa telemetría y budget por proyecto |

---

## 6. Ver telemetría y coste

```bash
# Estado del budget
curl -s https://seedy-api.neofarm.io/v1/code/telemetry \
  -H "Authorization: Bearer YOUR_KEY" | python -m json.tool

# Preview del routing sin hacer llamada
curl -s "https://seedy-api.neofarm.io/v1/code/route/preview?task_type=REFACTOR_MULTI&tier=balanced&context_tokens=5000" \
  -H "Authorization: Bearer YOUR_KEY" | python -m json.tool
```

Los datos de uso también se reflejan en el dashboard Grafana `coder_overview` en:
**seedy-grafana.neofarm.io**

---

## 7. Degradación automática de budget

El sistema monitorea el gasto diario (cap $5) y mensual (cap $100):

- Al **80%** del cap → aviso en el primer token del stream como comentario
- Al **95%** del cap → degrada automáticamente a Ollama local durante 1 hora

Puedes cambiar los caps con variables de entorno en `.env`:
```
CODER_DAILY_CAP_USD=10.0
CODER_MONTHLY_CAP_USD=200.0
```

---

## 8. Usar desde Cursor

Cursor también acepta proveedores OpenAI-compatible. En **Settings → Models → Add Model**:

- API Base: `https://seedy-api.neofarm.io/v1/code`
- API Key: tu SEEDY_API_KEY
- Model: `seedy-auto`

---

## 9. Ejemplo de uso local sin Cloudflare (desarrollo)

```yaml
- name: Seedy Dev
  provider: openai
  apiBase: http://localhost:8000/v1/code
  apiKey: sk-seedy-local
  model: seedy-auto
```
