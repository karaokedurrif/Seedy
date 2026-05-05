# OpenClaw Mini PC → Ollama DGX (Sin Coste)

## 🎯 Objetivo

Configurar **OpenClaw** en el mini PC (192.168.20.54) para usar los modelos **Ollama del DGX** (192.168.20.57:11434) en lugar de APIs de pago (OpenAI, Anthropic, etc.).

---

## 📋 Arquitectura

```
┌─────────────────────────────────────────────┐
│  Mini PC (192.168.20.54)                    │
│  ┌─────────────────────────────────────┐    │
│  │  OpenClaw                           │    │
│  │  Tareas automatizadas               │    │
│  └─────────────────────────────────────┘    │
│              │                               │
│              │ Ollama API Compatible         │
│              ↓                               │
└──────────────┼───────────────────────────────┘
               │
               │ http://192.168.20.57:11434
               ↓
┌─────────────────────────────────────────────┐
│  DGX Spark (192.168.20.57)                  │
│  ┌─────────────────────────────────────┐    │
│  │  Ollama + GPU RTX 5080              │    │
│  │  Modelos:                           │    │
│  │  - qwen2.5:7b (rápido)             │    │
│  │  - qwen2.5:72b (lento)             │    │
│  │  - seedy:v16 (ganadería)           │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**Coste: $0** — Sin APIs externas, todo local

---

## 🔧 Configuración OpenClaw

OpenClaw usa variables de entorno para configurar el proveedor de LLM. Hay **2 métodos**:

### Método 1: Variables de Entorno (Recomendado)

#### 1. Editar archivo de configuración

```bash
# Desde el mini PC
cd ~/openclaw  # O donde esté instalado OpenClaw

# Editar .env o crear si no existe
nano .env
```

#### 2. Añadir configuración Ollama

```bash
# ============================================
# CONFIGURACIÓN OLLAMA (DGX) - SIN COSTE
# ============================================

# Proveedor: Ollama (compatible con OpenAI API)
LLM_PROVIDER=ollama

# Endpoint del Ollama en el DGX
OLLAMA_BASE_URL=http://192.168.20.57:11434

# Modelo por defecto (elige uno)
OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M

# Alternativamente, para análisis complejos:
# OLLAMA_MODEL=qwen2.5:72b-instruct-q4_K_M

# O para consultas ganadería:
# OLLAMA_MODEL=seedy:v16

# ============================================
# DESACTIVAR APIS DE PAGO (IMPORTANTE)
# ============================================

# Comentar o eliminar estas líneas si existen:
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# TOGETHER_API_KEY=...

# O dejarlas vacías:
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
TOGETHER_API_KEY=
```

#### 3. Reiniciar OpenClaw

```bash
# Dependiendo de cómo lo ejecutes:

# Si es Docker:
docker compose restart

# Si es Python directo:
# Parar proceso actual (Ctrl+C) y volver a ejecutar
python -m openclaw

# Si es systemd service:
sudo systemctl restart openclaw
```

---

### Método 2: Configuración en Código (Si modificas OpenClaw)

Si tienes acceso al código de OpenClaw y quieres hardcodear la configuración:

```python
# En tu archivo de configuración de OpenClaw (ej: config.py o main.py)

import os

# Configuración Ollama
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_BASE_URL"] = "http://192.168.20.57:11434"
os.environ["OLLAMA_MODEL"] = "qwen2.5:7b-instruct-q4_K_M"

# Desactivar APIs de pago
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
```

---

## 🤖 Modelos Disponibles

| Modelo | Tamaño | Velocidad | Recomendado para |
|--------|--------|-----------|------------------|
| **qwen2.5:7b-instruct-q4_K_M** | 4.7 GB | 20-30 tok/s | ✅ Tareas generales, rápido |
| **qwen2.5:72b-instruct-q4_K_M** | 47 GB | 4.3 tok/s | Análisis profundos (lento) |
| **seedy:v16** | 9 GB | 15-20 tok/s | Consultas ganadería específicas |

**💡 Recomendación:** Empieza con `qwen2.5:7b` para tareas generales. Es rápido y funciona bien.

---

## 🧪 Verificar Configuración

### 1. Test de conectividad

Desde el mini PC:

```bash
# Verificar que puedes alcanzar el Ollama del DGX
curl http://192.168.20.57:11434/api/tags

# Debería listar los modelos disponibles
```

### 2. Test simple con Ollama

```bash
# Hacer una consulta de prueba
curl -X POST http://192.168.20.57:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b-instruct-q4_K_M",
    "prompt": "Di hola en español",
    "stream": false
  }'
```

### 3. Test desde OpenClaw

Ejecuta una tarea simple desde OpenClaw y verifica que:
- ✅ No aparecen errores de API key
- ✅ Las respuestas llegan rápidamente
- ✅ No hay cobros en tus cuentas de OpenAI/Anthropic

---

## 📊 Comparativa Coste

| Proveedor | Modelo | Coste por 1M tokens | Coste mensual (100 tareas) |
|-----------|--------|---------------------|---------------------------|
| **OpenAI** | GPT-4 | $30 entrada + $60 salida | ~$45/mes |
| **Anthropic** | Claude 3.5 Sonnet | $3 entrada + $15 salida | ~$9/mes |
| **Ollama DGX** | qwen2.5:7b | $0 | **$0/mes** ✅ |
| **Ollama DGX** | qwen2.5:72b | $0 | **$0/mes** ✅ |

**Ahorro:** $45-$540/año dependiendo del uso

---

## 🔧 Configuración Avanzada

### Cambiar modelo según tarea

Si OpenClaw permite especificar modelo por tarea:

```python
# Tareas rápidas
model_rapido = "qwen2.5:7b-instruct-q4_K_M"

# Tareas complejas (análisis, razonamiento)
model_complejo = "qwen2.5:72b-instruct-q4_K_M"

# Tareas específicas ganadería
model_ganaderia = "seedy:v16"
```

### Timeout y reintentos

```bash
# En .env
OLLAMA_TIMEOUT=60  # segundos
OLLAMA_MAX_RETRIES=3
```

### Temperatura y parámetros

```python
# Configuración típica para Ollama
parameters = {
    "temperature": 0.7,      # Creatividad (0-1)
    "top_p": 0.9,           # Nucleus sampling
    "top_k": 40,            # Top-k sampling
    "num_predict": 2048,    # Max tokens respuesta
}
```

---

## 🐛 Troubleshooting

### Problema 1: "Connection refused" o "Cannot connect"

**Causa:** OpenClaw no puede alcanzar el DGX.

**Solución:**

```bash
# 1. Verificar conectividad básica
ping 192.168.20.57

# 2. Verificar que el puerto 11434 esté abierto
telnet 192.168.20.57 11434
# O con nc:
nc -zv 192.168.20.57 11434

# 3. Verificar que Ollama esté corriendo en el DGX
ssh daviddgx@192.168.20.57 "docker ps | grep ollama"

# 4. Verificar que Ollama escuche en 0.0.0.0
ssh daviddgx@192.168.20.57 "docker exec ollama sh -c 'echo \$OLLAMA_HOST'"
# Debe devolver: 0.0.0.0:11434
```

### Problema 2: "Model not found"

**Causa:** El modelo especificado no existe en el DGX.

**Solución:**

```bash
# Ver modelos disponibles
curl http://192.168.20.57:11434/api/tags

# O desde el DGX:
ssh daviddgx@192.168.20.57 "docker exec ollama ollama list"

# Usar exactamente el nombre que aparece, ej:
# qwen2.5:7b-instruct-q4_K_M
# NO: qwen2.5:7b (sin el sufijo completo)
```

### Problema 3: Respuestas muy lentas con qwen2.5:72b

**Causa:** El modelo 72B en el DGX va a 4.3 tok/s (limitación hardware).

**Solución:** Usa `qwen2.5:7b` para tareas interactivas. Reserva el 72B solo para análisis que requieran razonamiento profundo.

### Problema 4: OpenClaw sigue usando APIs de pago

**Causa:** Las variables de entorno no se cargaron correctamente.

**Solución:**

```bash
# Verificar variables activas
env | grep -E 'OLLAMA|OPENAI|ANTHROPIC'

# Asegurarse de que .env se carga
# Si usas Docker, reinicia completamente:
docker compose down && docker compose up -d

# Si es Python, verifica que se carga el .env:
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('OLLAMA_BASE_URL'))"
```

### Problema 5: "Unauthorized" o error de API key

**Causa:** Ollama no requiere API key, pero OpenClaw quizá la está enviando.

**Solución:**

```bash
# En .env, asegúrate de que NO hay estas líneas:
# OLLAMA_API_KEY=...

# Ollama es completamente abierto, no necesita autenticación
```

---

## 📝 Ejemplo Completo de Configuración

### Archivo `.env` completo para OpenClaw

```bash
# ============================================
# OPENCLAW CONFIGURACIÓN - OLLAMA DGX
# ============================================

# Proveedor LLM
LLM_PROVIDER=ollama

# Endpoint Ollama (DGX)
OLLAMA_BASE_URL=http://192.168.20.57:11434

# Modelo por defecto (rápido)
OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M

# Timeout (segundos)
OLLAMA_TIMEOUT=60

# Parámetros de generación
OLLAMA_TEMPERATURE=0.7
OLLAMA_MAX_TOKENS=2048

# ============================================
# DESACTIVAR APIS DE PAGO
# ============================================
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
TOGETHER_API_KEY=
GOOGLE_API_KEY=

# ============================================
# OTRAS CONFIGURACIONES OPENCLAW
# ============================================
# (mantén tus configuraciones existentes aquí)
LOG_LEVEL=INFO
WORKSPACE_PATH=./workspace
```

---

## 🚀 Comandos Útiles

```bash
# Ver logs de OpenClaw (si es Docker)
docker compose logs -f openclaw

# Ver logs de Ollama en el DGX
ssh daviddgx@192.168.20.57 "docker logs ollama --tail=50"

# Test rápido de Ollama desde mini PC
curl -s http://192.168.20.57:11434/api/tags | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['models']]"

# Monitorear uso de GPU en el DGX durante tareas
ssh daviddgx@192.168.20.57 "watch -n 1 nvidia-smi"
```

---

## ✅ Checklist de Verificación

Después de configurar, verifica:

- [ ] `curl http://192.168.20.57:11434/api/tags` devuelve lista de modelos
- [ ] Archivo `.env` tiene `OLLAMA_BASE_URL=http://192.168.20.57:11434`
- [ ] Variable `OLLAMA_MODEL` está configurada
- [ ] APIs de pago están desactivadas (keys vacías)
- [ ] OpenClaw reiniciado después de cambios
- [ ] Test de tarea simple funciona sin errores
- [ ] No hay cobros en cuentas de OpenAI/Anthropic

---

## 💡 Tips Finales

1. **Empieza con qwen2.5:7b** — Es rápido y funciona bien para la mayoría de tareas
2. **Guarda el .env original** — Por si necesitas volver a APIs de pago temporalmente
3. **Monitorea el DGX** — Asegúrate de que no sobrecargues la GPU si hay otros procesos
4. **Documenta tus prompts** — Los modelos locales responden diferente a los de pago

---

## 📚 Referencias

- **OpenClaw GitHub:** https://github.com/openclaw/openclaw
- **Ollama API Docs:** https://github.com/ollama/ollama/blob/main/docs/api.md
- **Seedy v4.6:** README.md en el repositorio

---

**Última actualización:** 5 mayo 2026  
**Versión:** 1.0  
**Autor:** Seedy Team
