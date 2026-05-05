#!/bin/bash
# Preparar upgrade de Openclaw desde el portátil MSI
# Genera paquete para transferir al mini PC Openclaw (192.168.20.54)
# Fecha: 5 mayo 2026

set -e

echo "📦 PREPARANDO UPGRADE OPENCLAW → vLLM 32B"
echo "=========================================="
echo ""

WORKSPACE="/home/davidia/Documentos/Seedy"
PACKAGE_DIR="/tmp/openclaw_upgrade_package"

# 1. Crear directorio temporal
echo "1️⃣ Creando paquete de upgrade..."
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"

# 2. Copiar script de upgrade
echo "   ✅ Script upgrade"
cp "$WORKSPACE/scripts/openclaw-upgrade-to-vllm-32b.sh" "$PACKAGE_DIR/"

# 3. Crear archivo .env con la configuración
echo "   ✅ Archivo .env"
cat > "$PACKAGE_DIR/openclaw.env" << 'EOF'
# Openclaw Configuration — vLLM Qwen2.5-Coder-32B-AWQ
# Actualizado: 5 mayo 2026

OLLAMA_BASE_URL=http://192.168.20.57:8001/v1
OLLAMA_MODEL=qwen2.5-coder-32b
OPENCLAW_API_KEY=e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4
OPENCLAW_SYSTEM_PROMPT=Eres un experto analista de sistemas operativos y monitoreo SOC. Analiza logs, métricas y eventos con precisión técnica. Responde en español.
OPENCLAW_TEMPERATURE=0.3
OPENCLAW_MAX_TOKENS=2000
OPENCLAW_LOG_LEVEL=INFO
EOF

# 4. Crear script de validación
echo "   ✅ Script validación"
cat > "$PACKAGE_DIR/test_openclaw_vllm.sh" << 'EOFTEST'
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

test_query 1 "CPU 95% constante en servidor Apache. ¿Qué verificar primero?"
test_query 2 "10 intentos de login SSH fallidos desde IP externa. Siguiente paso?"
test_query 3 "/var/log/ ocupa 80GB de disco. ¿Cómo identificar logs grandes y limpiar?"
test_query 4 "Uso de swap al 90% en servidor MySQL. Diagnosticar causa."
test_query 5 "Nginx devuelve 502 Bad Gateway. ¿Dónde buscar logs y qué verificar?"

echo ""
echo "=================================="
echo "✅ Validación completada"
EOFTEST

chmod +x "$PACKAGE_DIR/test_openclaw_vllm.sh"

# 5. Crear README de instrucciones rápidas
echo "   ✅ README"
cat > "$PACKAGE_DIR/README.txt" << 'EOFREADME'
OPENCLAW UPGRADE A vLLM 32B — INSTRUCCIONES RÁPIDAS
===================================================

Estás en el mini PC Openclaw (192.168.20.54)

PASO 1: Ejecutar upgrade automático
------------------------------------
./openclaw-upgrade-to-vllm-32b.sh

Esto hará:
- Backup de configuración actual
- Actualizar ~/.openclaw/.env
- Verificar conectividad DGX
- Reiniciar Openclaw
- Test automático

PASO 2 (ALTERNATIVO): Upgrade manual
-------------------------------------
Si el script falla, copia manualmente:

mkdir -p ~/.openclaw
cp openclaw.env ~/.openclaw/.env
systemctl --user restart openclaw

PASO 3: Validar funcionamiento
-------------------------------
./test_openclaw_vllm.sh

Debe mostrar 5 tests con respuestas técnicas detalladas.

TROUBLESHOOTING
---------------
- Ver logs: journalctl --user -u openclaw -f
- Test DGX: curl -s http://192.168.20.57:8001/health
- Rollback: Restaurar desde ~/.openclaw/backup_*/

Documentación completa: OPENCLAW_UPGRADE_INSTRUCTIONS.md
EOFREADME

# 6. Copiar documentación completa
echo "   ✅ Documentación"
cp "$WORKSPACE/docs/OPENCLAW_UPGRADE_INSTRUCTIONS.md" "$PACKAGE_DIR/"

# 7. Hacer todos los scripts ejecutables
chmod +x "$PACKAGE_DIR"/*.sh

# 8. Crear tarball comprimido
echo ""
echo "2️⃣ Comprimiendo paquete..."
cd /tmp
tar -czf openclaw_upgrade_vllm32b.tar.gz openclaw_upgrade_package/
TARBALL_SIZE=$(du -h openclaw_upgrade_vllm32b.tar.gz | awk '{print $1}')

echo "   ✅ Paquete creado: /tmp/openclaw_upgrade_vllm32b.tar.gz ($TARBALL_SIZE)"
echo ""

# 9. Resumen y opciones de transferencia
echo "=========================================="
echo "✅ PAQUETE LISTO PARA TRANSFERIR"
echo "=========================================="
echo ""
echo "📂 Ubicación: /tmp/openclaw_upgrade_vllm32b.tar.gz"
echo "📊 Tamaño: $TARBALL_SIZE"
echo "📁 Contenido:"
ls -lh "$PACKAGE_DIR" | tail -n +2 | awk '{print "   - " $9 " (" $5 ")"}'
echo ""
echo "🔄 OPCIONES DE TRANSFERENCIA:"
echo ""
echo "OPCIÓN 1: USB (recomendado si no hay SSH)"
echo "  1. Inserta USB en este portátil"
echo "  2. cp /tmp/openclaw_upgrade_vllm32b.tar.gz /media/davidia/USB/"
echo "  3. Desconecta USB y conéctalo al mini PC Openclaw"
echo "  4. En el mini PC:"
echo "     cd ~"
echo "     tar -xzf /media/*/openclaw_upgrade_vllm32b.tar.gz"
echo "     cd openclaw_upgrade_package"
echo "     ./openclaw-upgrade-to-vllm-32b.sh"
echo ""
echo "OPCIÓN 2: SCP (si SSH está habilitado)"
echo "  scp /tmp/openclaw_upgrade_vllm32b.tar.gz usuario@192.168.20.54:~/"
echo "  ssh usuario@192.168.20.54"
echo "  tar -xzf openclaw_upgrade_vllm32b.tar.gz"
echo "  cd openclaw_upgrade_package"
echo "  ./openclaw-upgrade-to-vllm-32b.sh"
echo ""
echo "OPCIÓN 3: HTTP simple server"
echo "  # En este portátil:"
echo "  cd /tmp"
echo "  python3 -m http.server 8888"
echo ""
echo "  # En el mini PC (desde navegador o terminal):"
echo "  wget http://192.168.20.131:8888/openclaw_upgrade_vllm32b.tar.gz"
echo "  tar -xzf openclaw_upgrade_vllm32b.tar.gz"
echo "  cd openclaw_upgrade_package"
echo "  ./openclaw-upgrade-to-vllm-32b.sh"
echo ""
echo "📖 Documentación completa: $PACKAGE_DIR/OPENCLAW_UPGRADE_INSTRUCTIONS.md"
echo ""
