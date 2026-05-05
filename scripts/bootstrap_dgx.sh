#!/bin/bash
# FASE 3: Bootstrap del DGX Spark para recibir Seedy + GeoTwin
# Ejecutar EN el DGX Spark (ARM64)
# Fecha: 30 abril 2026

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  BOOTSTRAP DGX SPARK (ARM64)${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# Verificar que estamos en ARM64
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ]; then
    echo -e "${RED}❌ Este script debe ejecutarse en ARM64/aarch64${NC}"
    echo "Arquitectura detectada: $ARCH"
    exit 1
fi
echo -e "${GREEN}✅ Arquitectura ARM64 confirmada${NC}"

# Verificar que somos el usuario correcto
if [ "$USER" != "davidia" ]; then
    echo -e "${YELLOW}⚠️  Se esperaba usuario 'davidia', detectado: $USER${NC}"
    read -p "¿Continuar de todas formas? (y/N): " continue_user
    [[ ! "$continue_user" =~ ^[Yy]$ ]] && exit 1
fi

echo ""
echo "=== PASO 1: Actualizar sistema ==="
sudo apt update
sudo apt upgrade -y
echo -e "${GREEN}✅ Sistema actualizado${NC}"

echo ""
echo "=== PASO 2: Instalar utilidades base ==="
sudo apt install -y \
    htop btop nvtop \
    curl wget git \
    tmux vim nano jq \
    python3-pip python3-venv \
    ntfs-3g exfat-fuse exfatprogs \
    rsync net-tools \
    build-essential \
    ca-certificates

echo -e "${GREEN}✅ Utilidades instaladas${NC}"

echo ""
echo "=== PASO 3: Verificar Docker ==="
if ! command -v docker &>/dev/null; then
    echo -e "${YELLOW}⚠️  Docker no encontrado, instalando...${NC}"
    
    # Instalar Docker (método oficial)
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    sudo usermod -aG docker $USER
    
    echo -e "${YELLOW}⚠️  Necesitas hacer logout/login para que docker group tome efecto${NC}"
else
    echo -e "${GREEN}✅ Docker ya instalado: $(docker --version)${NC}"
fi

# Verificar docker compose
if ! docker compose version &>/dev/null; then
    echo -e "${RED}❌ docker compose no funciona${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose: $(docker compose version)${NC}"

echo ""
echo "=== PASO 4: Verificar NVIDIA runtime para Docker ==="
if docker info 2>/dev/null | grep -q "Default Runtime: nvidia"; then
    echo -e "${GREEN}✅ NVIDIA runtime configurado${NC}"
else
    echo -e "${YELLOW}⚠️  NVIDIA runtime no configurado, intentando configurar...${NC}"
    
    # Instalar nvidia-container-toolkit si no está
    if ! command -v nvidia-ctk &>/dev/null; then
        distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
        
        sudo apt update
        sudo apt install -y nvidia-container-toolkit
    fi
    
    # Configurar runtime
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    
    echo -e "${GREEN}✅ NVIDIA runtime configurado${NC}"
fi

# Test GPU en Docker
echo ""
echo "Probando acceso GPU en contenedor..."
if docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi &>/dev/null; then
    echo -e "${GREEN}✅ GPU accesible desde Docker${NC}"
else
    echo -e "${RED}❌ GPU no accesible desde Docker${NC}"
    exit 1
fi

echo ""
echo "=== PASO 5: Instalar Tailscale (acceso remoto seguro) ==="
if ! command -v tailscale &>/dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    echo -e "${GREEN}✅ Tailscale instalado${NC}"
    echo ""
    echo -e "${YELLOW}Ejecuta manualmente para conectar:${NC}"
    echo "  sudo tailscale up --ssh"
else
    echo -e "${GREEN}✅ Tailscale ya instalado${NC}"
    tailscale status || echo "No conectado todavía"
fi

echo ""
echo "=== PASO 6: Crear estructura de directorios ==="
mkdir -p ~/seedy
mkdir -p ~/geotwin
mkdir -p ~/migration_dumps
mkdir -p ~/backups
mkdir -p /mnt/data/models
mkdir -p /mnt/data/knowledge
mkdir -p /mnt/data/datasets
mkdir -p /mnt/data/backups

# Permisos
sudo chown -R $USER:$USER /mnt/data 2>/dev/null || true

echo -e "${GREEN}✅ Estructura de directorios creada${NC}"

echo ""
echo "=== PASO 7: Crear red Docker compartida ==="
docker network create ai_default 2>/dev/null || echo "Red ai_default ya existe"
echo -e "${GREEN}✅ Red Docker creada${NC}"

echo ""
echo "=== PASO 8: Instalar Portainer Agent (opcional) ==="
read -p "¿Instalar Portainer Agent para gestión remota? (Y/n): " install_portainer

if [[ ! "$install_portainer" =~ ^[Nn]$ ]]; then
    docker run -d \
        -p 9001:9001 \
        --name portainer_agent \
        --restart=always \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v /var/lib/docker/volumes:/var/lib/docker/volumes \
        portainer/agent:latest || echo "Portainer Agent ya existe"
    
    echo -e "${GREEN}✅ Portainer Agent instalado en :9001${NC}"
    echo "Añádelo en Portainer del GEEKOM: http://192.168.20.54:9001"
fi

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  BOOTSTRAP COMPLETADO${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "DGX Spark preparado para recibir Seedy + GeoTwin"
echo ""
echo "Estado del sistema:"
echo "  - Docker: $(docker --version)"
echo "  - NVIDIA: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
echo "  - Arquitectura: $ARCH"
echo "  - Directorios: ~/seedy, ~/geotwin, /mnt/data/"
echo ""
echo "=== SIGUIENTE PASO ==="
echo "1. Montar disco externo 2TB en /mnt/data (si no está montado)"
echo "2. Restaurar volúmenes Docker:"
echo "     bash ~/seedy/scripts/restore_volumes.sh"
