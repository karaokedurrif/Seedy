# Adaptación docker-compose.yml para DGX Spark (ARM64)

## CAMBIOS NECESARIOS EN ~/seedy/docker-compose.yml

Ejecutar estos cambios EN EL DGX después de la transferencia.

---

### 1. Volúmenes - Rutas del disco externo

```yaml
# ANTES (portátil):
volumes:
  - /home/davidia/models:/models

# DESPUÉS (DGX):
volumes:
  - /mnt/data/models:/models
```

```yaml
# ANTES (portátil):
volumes:
  - ./conocimientos:/app/conocimientos:ro

# DESPUÉS (DGX):
volumes:
  - /mnt/data/knowledge:/app/conocimientos:ro
```

---

### 2. Servicio seedy-backend - Build para ARM64

```yaml
# ANTES (portátil):
seedy-backend:
  build: ./backend
  # ...

# DESPUÉS (DGX):
seedy-backend:
  build:
    context: ./backend
    dockerfile: Dockerfile
    # No necesita platform explicit si estás construyendo en ARM64 nativo
  # ...resto igual
```

Si el build falla con error de arquitectura:

```bash
# Construir manualmente forzando ARM64
cd ~/seedy/backend
docker build --platform linux/arm64 -t seedy-seedy-backend:latest .
```

---

### 3. Verificar imágenes base ARM64-compatible

Todas las imágenes del docker-compose actual YA son multi-arch:

- ✅ `ollama/ollama:latest` → ARM64 nativo
- ✅ `ghcr.io/open-webui/open-webui:v0.8.12` → ARM64 disponible
- ✅ `qdrant/qdrant:latest` → ARM64 nativo  
- ✅ `influxdb:2` → ARM64 disponible
- ✅ `grafana/grafana:latest` → ARM64 disponible
- ✅ `nodered/node-red:latest` → ARM64 nativo
- ✅ `eclipse-mosquitto:2` → ARM64 disponible
- ✅ `searxng/searxng:latest` → ARM64 disponible
- ✅ `caddy:2-alpine` → ARM64 disponible
- ✅ `alexxit/go2rtc:latest` → ARM64 disponible
- ✅ `cloudflare/cloudflared:latest` → ARM64 disponible
- ✅ `unclecode/crawl4ai:latest` → Verificar, puede no tener ARM64

Para `crawl4ai`, si falla:

```yaml
# Comentar temporalmente si no tiene ARM64
# crawl4ai:
#   image: unclecode/crawl4ai:latest
#   ...
```

---

### 4. Servicio go2rtc - Sin cámaras por ahora

```yaml
# ANTES (portátil):
go2rtc:
  image: alexxit/go2rtc:latest
  network_mode: host  # Acceso directo a cámaras VLAN 10.10.10.x
  volumes:
    - ./go2rtc.yaml:/config/go2rtc.yaml:ro

# DESPUÉS (DGX - temporal):
# Las cámaras NO están conectadas al DGX todavía (irán a la J3011)
# Comentar o dejar sin streams hasta migrar cámaras
go2rtc:
  image: alexxit/go2rtc:latest
  ports:
    - "1984:1984"  # Cambiar de host network a bridge normal
  volumes:
    - ./go2rtc.yaml:/config/go2rtc.yaml:ro
  networks:
    - ai_default
```

Editar `go2rtc.yaml` y comentar todos los streams de cámaras hasta que se conecten a la J3011.

---

### 5. Variables de entorno - Ajustar .env

En `~/seedy/.env`:

```bash
# Path al disco externo (cambiar si usas otra ruta)
MODELS_PATH=/mnt/data/models
KNOWLEDGE_PATH=/mnt/data/knowledge

# CORS - añadir IP del DGX si accedes desde otros hosts
CORS_ORIGINS=https://seedy.neofarm.io,https://seedy-api.neofarm.io,http://localhost:3000,http://192.168.20.54:3000

# API keys (mantener las mismas)
TOGETHER_API_KEY=<tu-key>
API_KEYS=sk-seedy-local,sk-ovosfera-0040464aeee532c89a9248a8f4667c0a,sk-firebait-openclaw

# Go2RTC URL - cambiar de host.docker.internal a nombre de servicio
GO2RTC_URL=http://go2rtc:1984
```

---

## SCRIPT DE ADAPTACIÓN AUTOMÁTICA

Crear en DGX: `~/seedy/adapt_for_arm64.sh`

```bash
#!/bin/bash
# Adaptar docker-compose.yml para DGX Spark ARM64

set -euo pipefail

cd ~/seedy

echo "Adaptando docker-compose.yml para ARM64..."

# Backup
cp docker-compose.yml docker-compose.yml.bak-x86

# Reemplazar rutas de volúmenes
sed -i 's|/home/davidia/models:/models|/mnt/data/models:/models|g' docker-compose.yml
sed -i 's|./conocimientos:/app/conocimientos|/mnt/data/knowledge:/app/conocimientos|g' docker-compose.yml

# Ajustar go2rtc (quitar host network temporalmente)
sed -i 's|network_mode: host|# network_mode: host  # Comentado - cámaras en J3011|g' docker-compose.yml

# Verificar .env existe
if [ ! -f .env ]; then
    cp .env.example .env 2>/dev/null || touch .env
fi

# Actualizar GO2RTC_URL en .env
if grep -q "GO2RTC_URL=" .env; then
    sed -i 's|GO2RTC_URL=.*|GO2RTC_URL=http://go2rtc:1984|g' .env
else
    echo "GO2RTC_URL=http://go2rtc:1984" >> .env
fi

echo "✅ docker-compose.yml adaptado para ARM64"
echo "Backup en: docker-compose.yml.bak-x86"
echo ""
echo "Siguiente paso:"
echo "  docker compose up -d"
```

Ejecutar:

```bash
chmod +x ~/seedy/adapt_for_arm64.sh
bash ~/seedy/adapt_for_arm64.sh
```

---

## VERIFICACIÓN POST-ADAPTACIÓN

```bash
# Verificar sintaxis
cd ~/seedy
docker compose config

# Ver qué imágenes va a usar
docker compose config --images

# Pull de imágenes (verificar ARM64)
docker compose pull

# Build del backend
docker compose build seedy-backend

# Levantar stack
docker compose up -d

# Ver logs en tiempo real
docker compose logs -f

# Verificar GPU en Ollama
docker exec ollama nvidia-smi

# Test de modelos
docker exec ollama ollama list
```

---

## TROUBLESHOOTING ARM64

### Error: "no matching manifest for linux/arm64"

```bash
# Identificar qué imagen falla
docker manifest inspect <imagen>:tag

# Solución 1: Usar tag específico ARM64
# Ejemplo: grafana/grafana:latest-ubuntu (tiene ARM64)

# Solución 2: Construir localmente
# Editar Dockerfile y construir:
docker build --platform linux/arm64 -t <imagen>:custom .
```

### Error: seedy-backend build falla

```bash
# Ver Dockerfile del backend
cat ~/seedy/backend/Dockerfile

# Si usa FROM python:3.11-slim, tiene ARM64
# Si usa otras bases, verificar:
docker manifest inspect python:3.11-slim | grep architecture

# Build verbose para ver dónde falla
docker build --platform linux/arm64 --progress=plain -t seedy-backend:debug ~/seedy/backend
```

### Ollama no ve modelos en /models

```bash
# Verificar montaje
docker exec ollama ls -la /models

# Si está vacío:
# 1. Verificar que el disco 2TB está montado
mount | grep /mnt/data

# 2. Verificar permisos
sudo chown -R 1000:1000 /mnt/data/models  # UID del usuario en contenedor

# 3. Copiar modelos del volumen al disco si es necesario
docker run --rm -v seedy_ollama_data:/source -v /mnt/data/models:/dest alpine \
  cp -r /source/. /dest/
```

---

## GeoTwin - Cambios similares

En `~/geotwin/docker-compose.yml`:

```yaml
# Cambiar rutas de assets/models si están en disco externo
volumes:
  - /mnt/data/geotwin_assets:/app/assets

# Verificar imágenes:
# - timescale/timescaledb-ha:pg16 → Tiene ARM64 ✅
# - Las imágenes custom geotwin-* necesitan rebuild en ARM64
```

---

*Documento generado para migración DGX Spark - 30 abril 2026*
