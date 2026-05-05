# Continue.dev + vLLM Qwen2.5-Coder-32B — Configuración MSI Portátil

**Fecha:** 5 mayo 2026  
**Estado:** ✅ CONFIGURADO  
**Endpoint:** http://192.168.20.57:8001/v1 (vLLM en DGX Spark)

---

## ✅ CONFIGURACIÓN COMPLETADA

**Archivo:** `~/.continue/config.json`

### Modelo configurado:
- **Modelo:** Qwen2.5-Coder-32B-Instruct-AWQ
- **Servidor:** vLLM en DGX Spark (192.168.20.57:8001)
- **Contexto:** 32,768 tokens
- **Temperatura:** 0.3 (chat), 0.2 (autocomplete)
- **Max tokens:** 2000 (chat), 100 (autocomplete)

---

## 🚀 CÓMO USAR

### 1. Reiniciar VS Code

La configuración ya está aplicada, pero **debes reiniciar VS Code** para que Continue.dev la cargue:

```bash
# Opción 1: Desde terminal
killall code && code ~/Documentos/Seedy

# Opción 2: Desde VS Code
Ctrl+Shift+P → "Developer: Reload Window"
```

### 2. Abrir Continue.dev

- **Atajo:** `Ctrl+L` (chat) o `Ctrl+I` (inline edit)
- **Sidebar:** Icono Continue en la barra lateral izquierda
- **Verificar modelo:** En la parte superior del chat debe aparecer "Qwen2.5-Coder-32B (vLLM DGX)"

### 3. Comandos personalizados

Ya configurados y listos para usar:

| Comando | Descripción | Atajo |
|---------|-------------|-------|
| `/explain` | Explicar código seleccionado | Selecciona + Ctrl+L + /explain |
| `/test` | Generar tests unitarios (pytest) | Selecciona + Ctrl+L + /test |
| `/optimize` | Optimizar código (rendimiento + legibilidad) | Selecciona + Ctrl+L + /optimize |
| `/docstring` | Añadir docstrings Google Style | Selecciona + Ctrl+L + /docstring |
| `/debug` | Buscar bugs y vulnerabilidades | Selecciona + Ctrl+L + /debug |
| `/edit` | Editar código inline | Ctrl+I |
| `/comment` | Añadir comentarios | Ctrl+I |
| `/commit` | Generar mensaje de commit | En Git Changes |

### 4. Tab Autocomplete

**Activado automáticamente** — mientras escribes código:

1. Escribe inicio de función/línea
2. Pausa 1-2 segundos
3. Continue.dev sugerirá completado en gris
4. **Tab** para aceptar, **Esc** para rechazar

**Ejemplo:**
```python
def calculate_factorial(n):
    # Presiona Tab aquí y Continue.dev completará la función
```

---

## 🧪 TESTS DE VALIDACIÓN

### Test 1: Chat básico

1. Abre Continue.dev (`Ctrl+L`)
2. Escribe: "Escribe una función Python para calcular factorial"
3. **Resultado esperado:** Código factorial completo en <30s

### Test 2: Explicar código

1. Selecciona esta función:
   ```python
   def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)
   ```
2. `Ctrl+L` → `/explain`
3. **Resultado esperado:** Explicación detallada de Fibonacci recursivo

### Test 3: Generar tests

1. Selecciona una función de `backend/services/`
2. `Ctrl+L` → `/test`
3. **Resultado esperado:** Tests pytest con casos edge

### Test 4: Tab autocomplete

1. Crea archivo nuevo `test_autocomplete.py`
2. Escribe: `def reverse_string(s):`
3. Enter y espera 2 segundos
4. **Resultado esperado:** Sugerencia de implementación en gris

### Test 5: Inline edit

1. Selecciona función con código mejorable
2. `Ctrl+I`
3. Escribe: "Añade type hints y manejo de errores"
4. **Resultado esperado:** Código editado inline con diff

---

## 📊 COMPARATIVA vs OTROS MODELOS

| Modelo | Calidad | Latencia | Contexto | Coste |
|--------|---------|----------|----------|-------|
| **Qwen2.5-Coder-32B (vLLM)** | **9/10** | **15-30s** | **32K** | **$0** |
| GitHub Copilot | 7/10 | 2-5s | 8K | $10/mes |
| GPT-4o (OpenAI) | 9.5/10 | 5-10s | 128K | $20-40/mes |
| CodeLlama-34B (local) | 7.5/10 | 40-60s | 16K | $0 |

**Ventajas vLLM 32B:**
- ✅ Gratis (infraestructura propia)
- ✅ Alta calidad (32B parámetros)
- ✅ Contexto suficiente (32K tokens)
- ✅ Privacidad total (local)

**Desventaja:**
- ⏱️ Latencia media-alta (15-30s primera query, 10-20s subsecuentes)
- 📡 Requiere DGX accesible (WiFi 192.168.20.x)

---

## 🛠️ TROUBLESHOOTING

### Problema 1: Continue.dev no carga modelo

**Síntomas:** Error "Failed to connect to model" o modelo no aparece en dropdown

**Solución:**
```bash
# 1. Verificar vLLM está corriendo
curl -s http://192.168.20.57:8001/health

# 2. Test endpoint directo
curl -X POST http://192.168.20.57:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4" \
  -d '{"model":"qwen2.5-coder-32b","messages":[{"role":"user","content":"test"}],"max_tokens":10}'

# 3. Revisar logs Continue.dev
# VS Code: View → Output → Continue (dropdown)

# 4. Reiniciar VS Code completamente
killall code && code ~/Documentos/Seedy
```

### Problema 2: Tab autocomplete no funciona

**Causas posibles:**
- Primera vez tarda ~20s en cargar modelo
- Contexto del archivo muy grande (>10K líneas)
- vLLM está procesando otra request

**Solución:**
```bash
# Verificar carga de vLLM
ssh daviddgx@192.168.20.57 "docker logs coder-vllm 2>&1 | tail -50"

# En VS Code: Continue settings
# Ctrl+Shift+P → "Preferences: Open Settings (JSON)"
# Añadir: "continue.enableTabAutocomplete": true
```

### Problema 3: Latencia muy alta (>60s)

**Primera query:** Normal (compilando CUDA graphs). Espera 2-3 queries.

**Queries posteriores:** vLLM puede estar ocupado con otra request (Openclaw, Coder Router, etc.)

**Monitoreo:**
```bash
# Ver requests activas en vLLM
ssh daviddgx@192.168.20.57 "docker logs coder-vllm 2>&1 | grep 'POST /v1/chat/completions' | tail -10"
```

### Problema 4: Respuestas en inglés

Continue.dev usa el modelo base sin instrucciones de idioma en system prompt por defecto.

**Solución:** Usa comandos personalizados (`/explain`, `/test`, etc.) que incluyen "en español" en el prompt.

O añade al inicio de cada query: "Responde en español:"

---

## 🔧 CONFIGURACIÓN AVANZADA

### Cambiar temperatura

Edita `~/.continue/config.json`:

```json
"completionOptions": {
  "temperature": 0.3,  // ← Cambiar aquí (0.0-1.0)
  "topP": 0.95,
  "maxTokens": 2000
}
```

### Añadir comando personalizado

```json
"customCommands": [
  {
    "name": "traducir",
    "prompt": "Traduce el siguiente código de {{{ input }}} a español, incluyendo comentarios y docstrings.",
    "description": "Traducir código a español"
  }
]
```

### Deshabilitar tab autocomplete (si molesta)

```json
"tabAutocompleteModel": null
```

O en VS Code settings:
```json
"continue.enableTabAutocomplete": false
```

---

## 📈 MÉTRICAS ESPERADAS

| Métrica | Valor objetivo |
|---------|----------------|
| Latencia primera query | 15-30s |
| Latencia queries subsecuentes | 10-20s |
| Tab autocomplete latency | 2-5s |
| Calidad código generado | 8.5-9/10 |
| Precisión refactorings | 9/10 |
| Tests generados (cobertura) | >80% |

---

## 🎯 CASOS DE USO ÓPTIMOS

### ✅ IDEAL para:
- Explicar código complejo (análisis profundo 32B)
- Generar tests exhaustivos (edge cases + mocks)
- Refactorings complejos (multi-archivo, arquitectura)
- Code reviews automatizados
- Debugging profundo (análisis de stack traces)

### ⚠️ SUBÓPTIMO para:
- Autocompletado ultra-rápido (<1s) — usar GitHub Copilot para esto
- Múltiples queries concurrentes — vLLM max 8 sesiones
- Contexto >32K tokens — truncar o usar GPT-4

---

## 📞 SOPORTE

**Logs Continue.dev:** VS Code → View → Output → Continue  
**Logs vLLM:** `ssh daviddgx@192.168.20.57 "docker logs coder-vllm"`  
**Health vLLM:** `curl -s http://192.168.20.57:8001/health`  
**Restart vLLM:** `ssh daviddgx@192.168.20.57 "cd ~/seedy/coder-vllm && docker compose restart"`

**Documentación completa:** `~/Documentos/Seedy/docs/vllm-coder-v4.7.md`

---

**Última actualización:** 5 mayo 2026  
**Versión:** v4.7 Continue.dev Client Config  
**Estado:** ✅ Producción — reiniciar VS Code para aplicar
