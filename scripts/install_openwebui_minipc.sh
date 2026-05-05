#!/bin/bash
# ==========================================
# INSTALACIÓN OPEN WEBUI EN MINI PC
# ==========================================
# Mini PC: 192.168.20.54
# DGX Ollama: 192.168.20.57:11434
# Sin coste - 100% local
# ==========================================

set -e

echo "🚀 INSTALACIÓN OPEN WEBUI EN MINI PC 192.168.20.54"
echo "📡 Conectando a Ollama del DGX: 192.168.20.57:11434"
echo ""

# Verificar conectividad con DGX
echo "1️⃣ Verificando conectividad con DGX..."
if curl -s http://192.168.20.57:11434/api/tags > /dev/null; then
    echo "✅ Conexión exitosa con Ollama del DGX"
    echo ""
    echo "Modelos disponibles:"
    curl -s http://192.168.20.57:11434/api/tags | python3 -c "import sys,json; models=json.load(sys.stdin)['models']; [print(f\"  - {m['name']} ({m['size']//1e9:.1f} GB)\") for m in models]"
else
    echo "❌ ERROR: No se puede conectar con Ollama del DGX"
    echo "Verifica que el DGX esté encendido y accesible"
    exit 1
fi

echo ""
echo "2️⃣ Creando directorio de trabajo..."
mkdir -p ~/openwebui
cd ~/openwebui

echo ""
echo "3️⃣ Creando docker-compose.yml..."
cat > docker-compose.yml << 'EOFCOMPOSE'
version: '3.8'

services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui-minipc
    ports:
      - "3000:8080"
    environment:
      # ⚡ CONFIGURACIÓN CRÍTICA: Apuntar al Ollama del DGX
      - OLLAMA_BASE_URL=http://192.168.20.57:11434
      
      # Nombre personalizado
      - WEBUI_NAME=Seedy Open WebUI (Mini PC)
      
      # Sin autenticación (red local segura)
      - WEBUI_AUTH=False
      
      # O si prefieres con autenticación, descomenta estas líneas:
      # - WEBUI_AUTH=True
      # - WEBUI_SECRET_KEY=seedy-minipc-secret-2026
      
      # Configuración adicional
      - ENABLE_OLLAMA_API=true
      - ENABLE_MODEL_FILTER=false
      
    volumes:
      - open-webui-data:/app/backend/data
    
    restart: unless-stopped
    
    # Healthcheck
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  open-webui-data:
    driver: local
EOFCOMPOSE

echo "✅ docker-compose.yml creado"

echo ""
echo "4️⃣ Levantando Open WebUI..."
docker compose up -d

echo ""
echo "5️⃣ Esperando que el servicio esté listo..."
sleep 10

echo ""
echo "6️⃣ Verificando estado..."
docker compose ps

echo ""
echo "7️⃣ Verificando logs iniciales..."
docker compose logs --tail=20

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ INSTALACIÓN COMPLETADA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Acceso Web:"
echo "   http://192.168.20.54:3000"
echo ""
echo "🤖 Modelos disponibles (desde DGX):"
echo "   - qwen2.5:7b-instruct-q4_K_M (rápido, chat general)"
echo "   - qwen2.5:72b-instruct-q4_K_M (lento, análisis complejo)"
echo "   - seedy:v16 (fine-tuned ganadería)"
echo ""
echo "💰 Coste: \$0 (100% local, sin APIs externas)"
echo ""
echo "📝 Comandos útiles:"
echo "   Ver logs:      docker compose logs -f"
echo "   Reiniciar:     docker compose restart"
echo "   Parar:         docker compose stop"
echo "   Arrancar:      docker compose start"
echo "   Estado:        docker compose ps"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
