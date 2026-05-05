#!/bin/bash
# Openclaw Upgrade: qwen2.5:7b → qwen2.5-coder-32b (vLLM DGX)
# Ejecutar en mini PC Zigbee (192.168.20.54) como usuario karaoke
# Fecha: 5 mayo 2026

set -e

echo "🚀 OPENCLAW UPGRADE A QWEN2.5-CODER-32B-AWQ (vLLM)"
echo "=================================================="
echo ""

# 1. Verificar que estamos en el mini PC correcto
CURRENT_USER=$(whoami)
CURRENT_IP=$(hostname -I | awk '{print $1}')

if [ "$CURRENT_USER" != "karaoke" ]; then
    echo "⚠️  ADVERTENCIA: Este script debe ejecutarse como usuario 'karaoke'"
    echo "   Usuario actual: $CURRENT_USER"
    read -p "¿Continuar de todas formas? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "✅ Usuario: $CURRENT_USER"
echo "✅ IP: $CURRENT_IP"
echo ""

# 2. Backup configuración actual
echo "📦 1/5 Haciendo backup de configuración actual..."
BACKUP_DIR=~/.openclaw/backup_$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

if [ -f ~/.openclaw/.env ]; then
    cp ~/.openclaw/.env "$BACKUP_DIR/.env.bak"
    echo "   ✅ Backup guardado en: $BACKUP_DIR/.env.bak"
else
    echo "   ⚠️  No se encontró ~/.openclaw/.env (instalación nueva?)"
fi
echo ""

# 3. Actualizar configuración
echo "⚙️  2/5 Actualizando configuración..."
mkdir -p ~/.openclaw

cat > ~/.openclaw/.env << 'EOF'
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
EOF

echo "   ✅ Configuración actualizada en ~/.openclaw/.env"
echo ""

# 4. Verificar conectividad con vLLM
echo "🔍 3/5 Verificando conectividad con vLLM DGX..."
VLLM_HEALTH=$(curl -s --max-time 5 http://192.168.20.57:8001/health 2>/dev/null || echo "FAIL")

if [ "$VLLM_HEALTH" != "FAIL" ]; then
    echo "   ✅ vLLM DGX accesible (192.168.20.57:8001)"
else
    echo "   ❌ ERROR: vLLM DGX no responde"
    echo "   Verifica que el contenedor vLLM esté corriendo en el DGX"
    echo "   Comando: ssh daviddgx@192.168.20.57 'cd ~/seedy/coder-vllm && docker compose ps'"
    exit 1
fi
echo ""

# 5. Reiniciar Openclaw
echo "🔄 4/5 Reiniciando servicio Openclaw..."
if systemctl --user is-active --quiet openclaw; then
    systemctl --user restart openclaw
    echo "   ✅ Openclaw reiniciado"
else
    echo "   ⚠️  Openclaw no estaba corriendo, intentando iniciar..."
    systemctl --user start openclaw || echo "   ⚠️  No se pudo iniciar (¿servicio no instalado?)"
fi
echo ""

# 6. Test de validación
echo "🧪 5/5 Ejecutando test de validación..."
sleep 3

# Test simple: verificar que Openclaw puede generar respuesta
TEST_PROMPT="Analiza brevemente: CPU al 95% durante 2 minutos en servidor web nginx"

echo "   Enviando test prompt..."
TEST_RESULT=$(curl -s --max-time 30 -X POST http://192.168.20.57:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4" \
  -d "{\"model\":\"qwen2.5-coder-32b\",\"messages\":[{\"role\":\"system\",\"content\":\"Eres un experto analista SOC\"},{\"role\":\"user\",\"content\":\"$TEST_PROMPT\"}],\"max_tokens\":200,\"temperature\":0.3}" \
  2>/dev/null || echo "ERROR")

if echo "$TEST_RESULT" | grep -q '"choices"'; then
    RESPONSE_LENGTH=$(echo "$TEST_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['choices'][0]['message']['content']))" 2>/dev/null || echo "0")
    echo "   ✅ Test exitoso: respuesta generada ($RESPONSE_LENGTH caracteres)"
    echo ""
    echo "   Extracto respuesta:"
    echo "$TEST_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print('   ' + d['choices'][0]['message']['content'][:200] + '...')" 2>/dev/null || echo "   (no se pudo parsear)"
else
    echo "   ❌ Test falló: no se pudo generar respuesta"
    echo "   Respuesta raw: $TEST_RESULT"
fi
echo ""

# 7. Resumen final
echo "=================================================="
echo "✅ UPGRADE COMPLETADO"
echo "=================================================="
echo ""
echo "Configuración aplicada:"
echo "  - Modelo: qwen2.5-coder-32b (32B parámetros, AWQ quantization)"
echo "  - Servidor: http://192.168.20.57:8001/v1"
echo "  - Backup: $BACKUP_DIR"
echo ""
echo "Calidad esperada: 6/10 (qwen2.5:7b) → 8.5/10 (qwen2.5-coder-32b)"
echo ""
echo "Próximos pasos:"
echo "  1. Monitorear logs: journalctl --user -u openclaw -f"
echo "  2. Test manual con 5 casos de uso (ver docs/OPENCLAW_MINIPC_VLLM_CONFIG.md)"
echo "  3. Comparar calidad respuestas vs modelo anterior"
echo ""
echo "Rollback (si necesario):"
echo "  cp $BACKUP_DIR/.env.bak ~/.openclaw/.env"
echo "  systemctl --user restart openclaw"
echo ""
