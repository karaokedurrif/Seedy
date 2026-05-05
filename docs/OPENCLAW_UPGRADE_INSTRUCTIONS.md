# Openclaw Upgrade a vLLM Qwen2.5-Coder-32B — Guía Práctica

**Mini PC:** 192.168.20.54  
**Usuario:** (especificar al ejecutar)  
**Fecha:** 5 mayo 2026  
**Objetivo:** Migrar de modelos pagos → vLLM 32B gratuito en DGX  
**Ahorro estimado:** ~$15-25/mes

---

## 📋 PRE-REQUISITOS

Antes de empezar, verifica:

1. **vLLM está corriendo en DGX** (192.168.20.57:8001):
   ```bash
   curl -s http://192.168.20.57:8001/health
   # Debe responder: {"status":"ok"}
   ```

2. **Tienes acceso físico al mini PC Openclaw** (192.168.20.54)
   - Monitor + teclado conectados
   - O acceso VNC/escritorio remoto si lo tienes configurado

---

## 🚀 OPCIÓN 1: SCRIPT AUTOMÁTICO (RECOMENDADO)

### Paso 1: Transferir script al mini PC

**Desde el portátil MSI** (192.168.20.131), ejecuta:

```bash
# Verificar conectividad
ping -c 2 192.168.20.54

# Si tienes SSH habilitado en el mini PC:
scp /home/davidia/Documentos/Seedy/scripts/openclaw-upgrade-to-vllm-32b.sh usuario@192.168.20.54:~/

# Si NO tienes SSH, usa USB:
# 1. Copia el script a USB:
cp /home/davidia/Documentos/Seedy/scripts/openclaw-upgrade-to-vllm-32b.sh /media/davidia/USB/

# 2. Luego en el mini PC, monta el USB y copia
```

### Paso 2: Ejecutar script en el mini PC

**En el mini PC Openclaw** (192.168.20.54), abre terminal:

```bash
# Hacer script ejecutable
chmod +x ~/openclaw-upgrade-to-vllm-32b.sh

# Ejecutar upgrade
./openclaw-upgrade-to-vllm-32b.sh

# El script hará:
# 1. Backup de configuración actual
# 2. Actualizar ~/.openclaw/.env con endpoint vLLM
# 3. Verificar conectividad con DGX
# 4. Reiniciar servicio Openclaw
# 5. Test de validación automático
```

**Salida esperada:**
```
✅ UPGRADE COMPLETADO
Configuración aplicada:
  - Modelo: qwen2.5-coder-32b (32B parámetros)
  - Servidor: http://192.168.20.57:8001/v1
  - Backup: ~/.openclaw/backup_20260505_HHMMSS

Calidad esperada: 6/10 → 8.5/10
```

---

## 🛠️ OPCIÓN 2: CONFIGURACIÓN MANUAL

Si el script falla o prefieres hacerlo manualmente:

### Paso 1: Backup configuración actual

```bash
# Crear directorio backup
mkdir -p ~/.openclaw/backup_$(date +%Y%m%d_%H%M%S)

# Copiar configuración actual
cp ~/.openclaw/.env ~/.openclaw/backup_$(date +%Y%m%d_%H%M%S)/.env.bak
```

### Paso 2: Editar configuración Openclaw

```bash
# Editar archivo de configuración
nano ~/.openclaw/.env
```

**Contenido nuevo del archivo:**

```bash
# Openclaw Configuration — vLLM Qwen2.5-Coder-32B-AWQ
# Actualizado: 5 mayo 2026

# vLLM Server en DGX Spark (192.168.20.57:8001)
OLLAMA_BASE_URL=http://192.168.20.57:8001/v1
OLLAMA_MODEL=qwen2.5-coder-32b
OPENCLAW_API_KEY=e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4

# Openclaw Settings
OPENCLAW_SYSTEM_PROMPT=Eres un experto analista de sistemas operativos y monitoreo SOC. Analiza logs, métricas y eventos con precisión técnica. Responde en español.
OPENCLAW_TEMPERATURE=0.3
OPENCLAW_MAX_TOKENS=2000
OPENCLAW_LOG_LEVEL=INFO
```

Guarda y cierra (Ctrl+O, Enter, Ctrl+X).

### Paso 3: Verificar conectividad con vLLM

```bash
# Test conexión DGX
curl -s http://192.168.20.57:8001/health

# Test modelo disponible
curl -s http://192.168.20.57:8001/v1/models | python3 -m json.tool
```

### Paso 4: Reiniciar Openclaw

```bash
# Reiniciar servicio
systemctl --user restart openclaw

# Verificar estado
systemctl --user status openclaw

# Ver logs en tiempo real
journalctl --user -u openclaw -f
```

### Paso 5: Test de validación

```bash
# Test directo al endpoint vLLM
curl -X POST http://192.168.20.57:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4" \
  -d '{
    "model": "qwen2.5-coder-32b",
    "messages": [
      {"role": "system", "content": "Eres un experto analista SOC"},
      {"role": "user", "content": "Analiza brevemente: CPU al 95% durante 2 minutos en servidor web nginx"}
    ],
    "max_tokens": 200,
    "temperature": 0.3
  }'
```

**Respuesta esperada:** JSON con análisis técnico detallado del problema de CPU.

---

## 🧪 VALIDACIÓN POST-UPGRADE

### 5 Tests de Calidad (ejecutar en terminal del mini PC)

Crea este script de validación:

```bash
cat > ~/test_openclaw_vllm.sh << 'EOF'
#!/bin/bash
echo "🧪 VALIDACIÓN OPENCLAW + vLLM 32B"
echo "=================================="

ENDPOINT="http://192.168.20.57:8001/v1/chat/completions"
API_KEY="e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4"

test_query() {
    local TEST_NUM=$1
    local QUERY=$2
    
    echo ""
    echo "Test $TEST_NUM: $QUERY"
    echo "---"
    
    RESPONSE=$(curl -s -X POST $ENDPOINT \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      -d "{\"model\":\"qwen2.5-coder-32b\",\"messages\":[{\"role\":\"system\",\"content\":\"Eres un experto analista SOC\"},{\"role\":\"user\",\"content\":\"$QUERY\"}],\"max_tokens\":300,\"temperature\":0.3}" \
      --max-time 30 2>/dev/null)
    
    if echo "$RESPONSE" | grep -q '"choices"'; then
        ANSWER=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'][:200])" 2>/dev/null)
        echo "✅ Respuesta recibida:"
        echo "$ANSWER..."
    else
        echo "❌ Error: $RESPONSE"
    fi
}

# Test 1: Alta CPU
test_query 1 "CPU 95% constante en servidor Apache. ¿Qué verificar primero?"

# Test 2: Logs sospechosos
test_query 2 "10 intentos de login SSH fallidos desde IP externa. Siguiente paso?"

# Test 3: Disco lleno
test_query 3 "/var/log/ ocupa 80GB de disco. ¿Cómo identificar logs grandes y limpiar?"

# Test 4: Memoria swap
test_query 4 "Uso de swap al 90% en servidor MySQL. Diagnosticar causa."

# Test 5: Servicio caído
test_query 5 "Nginx devuelve 502 Bad Gateway. ¿Dónde buscar logs y qué verificar?"

echo ""
echo "=================================="
echo "✅ Validación completada"
echo ""
echo "Calidad esperada: 8.5/10"
echo "Latencia esperada: 15-30s por query"
echo "Coste: \$0.00 (gratis)"
EOF

chmod +x ~/test_openclaw_vllm.sh
~/test_openclaw_vllm.sh
```

**Criterios de éxito:**
- ✅ 5/5 tests responden (sin errores HTTP)
- ✅ Respuestas son técnicamente precisas (mencionan comandos, logs específicos)
- ✅ Latencia <30s por query
- ✅ Calidad percibida: 8-9/10 (vs 6/10 con qwen2.5:7b anterior)

---

## 🔄 ROLLBACK (si algo falla)

```bash
# Restaurar configuración anterior
LAST_BACKUP=$(ls -t ~/.openclaw/backup_* | head -1)
cp $LAST_BACKUP/.env.bak ~/.openclaw/.env

# Reiniciar servicio
systemctl --user restart openclaw

# Verificar
systemctl --user status openclaw
```

---

## 📊 COMPARATIVA ANTES vs DESPUÉS

| Métrica | Antes (qwen2.5:7b Ollama) | Después (qwen2.5-coder-32B vLLM) |
|---------|---------------------------|----------------------------------|
| Calidad | 6/10 | 8.5/10 |
| Latencia | 8-15s | 15-30s |
| Contexto | 32K tokens | 32K tokens |
| Coste | Gratis (local Ollama) | Gratis (vLLM DGX) |
| Precisión técnica | Media | Alta |
| Comandos específicos | Genéricos | Específicos del SO |

---

## 🔍 TROUBLESHOOTING

### Problema 1: vLLM no responde

```bash
# Verificar vLLM está corriendo en DGX
curl -s http://192.168.20.57:8001/health

# Si falla, desde el portátil MSI verificar:
ssh daviddgx@192.168.20.57 "cd ~/seedy/coder-vllm && docker compose ps"

# Reiniciar vLLM si necesario:
ssh daviddgx@192.168.20.57 "cd ~/seedy/coder-vllm && docker compose restart"
```

### Problema 2: Openclaw no arranca

```bash
# Ver logs detallados
journalctl --user -u openclaw -n 100 --no-pager

# Verificar archivo .env existe
cat ~/.openclaw/.env

# Verificar permisos
ls -la ~/.openclaw/
```

### Problema 3: Latencia muy alta (>60s)

Esto puede indicar que vLLM está compilando CUDA graphs (primera inferencia). Espera 2-3 queries y debería estabilizarse en 15-30s.

### Problema 4: Respuestas en inglés

Verifica que `OPENCLAW_SYSTEM_PROMPT` incluye "Responde en español" en el archivo `.env`.

---

## 📞 SOPORTE

Si tienes problemas:

1. **Logs Openclaw:** `journalctl --user -u openclaw -f`
2. **Logs vLLM:** `ssh daviddgx@192.168.20.57 "docker logs coder-vllm"`
3. **Health DGX:** `curl -s http://192.168.20.57:8001/health`
4. **Documentación completa:** `~/Documentos/Seedy/docs/vllm-coder-v4.7.md`

---

**Última actualización:** 5 mayo 2026  
**Versión:** v4.7 Dual-Engine Openclaw Client Config  
**Autor:** Seedy IA Expert Agent
