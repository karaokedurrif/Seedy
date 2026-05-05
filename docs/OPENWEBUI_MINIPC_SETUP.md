# Open WebUI en Mini PC — Configuración sin Coste

## 🎯 Objetivo

Instalar **Open WebUI** en el mini PC (192.168.20.54) para usar los modelos de **Ollama del DGX** (192.168.20.57) sin coste alguno.

---

## 📋 Arquitectura

```
┌─────────────────────────────────────────────┐
│  Mini PC (192.168.20.54)                    │
│  ┌─────────────────────────────────────┐    │
│  │  Open WebUI                         │    │
│  │  Puerto: 3000                       │    │
│  │  RAM: ~200 MB                       │    │
│  │  CPU: mínimo                        │    │
│  └─────────────────────────────────────┘    │
│              │                               │
│              │ HTTP API                      │
│              ↓                               │
└──────────────┼───────────────────────────────┘
               │
               │ http://192.168.20.57:11434
               ↓
┌─────────────────────────────────────────────┐
│  DGX Spark (192.168.20.57)                  │
│  ┌─────────────────────────────────────┐    │
│  │  Ollama + GPU RTX 5080              │    │
│  │  Puerto: 11434                      │    │
│  │  Modelos:                           │    │
│  │  - qwen2.5:7b (4.7 GB, rápido)     │    │
│  │  - qwen2.5:72b (47 GB, lento)      │    │
│  │  - seedy:v16 (9 GB, ganadería)     │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**✅ Ventajas:**
- Mini PC solo ejecuta el frontend web (ligero)
- Toda la inferencia GPU ocurre en el DGX
- **Coste: $0** (100% local, sin APIs externas)
- Sin límites de uso

---

## 🚀 Instalación Rápida

### Desde el MSI (copiar script al mini PC)

```bash
# 1. Copiar script al mini PC
scp ~/Documentos/Seedy/scripts/install_openwebui_minipc.sh usuario@192.168.20.54:~/

# 2. Conectar al mini PC
ssh usuario@192.168.20.54

# 3. Ejecutar instalación
bash ~/install_openwebui_minipc.sh
```

El script hará:
1. Verificar conectividad con DGX
2. Listar modelos disponibles
3. Crear `docker-compose.yml` con la configuración correcta
4. Levantar Open WebUI
5. Verificar estado

---

## 📝 Instalación Manual

Si prefieres hacerlo paso a paso:

### 1. Verificar Conectividad

```bash
# Desde el mini PC
curl http://192.168.20.57:11434/api/tags
```

Deberías ver la lista de modelos del DGX.

### 2. Crear directorio

```bash
mkdir -p ~/openwebui && cd ~/openwebui
```

### 3. Crear docker-compose.yml

```yaml
version: '3.8'

services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui-minipc
    ports:
      - "3000:8080"
    environment:
      # ⚡ CRÍTICO: Apuntar al Ollama del DGX
      - OLLAMA_BASE_URL=http://192.168.20.57:11434
      
      # Nombre personalizado
      - WEBUI_NAME=Seedy Open WebUI (Mini PC)
      
      # Sin autenticación (red local)
      - WEBUI_AUTH=False
      
      # Configuración adicional
      - ENABLE_OLLAMA_API=true
      - ENABLE_MODEL_FILTER=false
      
    volumes:
      - open-webui-data:/app/backend/data
    
    restart: unless-stopped

volumes:
  open-webui-data:
```

### 4. Levantar servicio

```bash
docker compose up -d
```

### 5. Verificar logs

```bash
docker compose logs -f
```

---

## 🌐 Acceso

```
http://192.168.20.54:3000
```

---

## 🤖 Modelos Disponibles

Al acceder a Open WebUI, verás estos modelos (del DGX):

| Modelo | Tamaño | Velocidad | Recomendado para |
|--------|--------|-----------|------------------|
| **qwen2.5:7b-instruct-q4_K_M** | 4.7 GB | 20-30 tok/s | Chat general, código, consultas rápidas |
| **qwen2.5:72b-instruct-q4_K_M** | 47 GB | 4.3 tok/s | Análisis profundo, razonamiento complejo |
| **seedy:v16** | 9 GB | 15-20 tok/s | Consultas ganadería (IoT, nutrición, genética) |
| **mxbai-embed-large** | 0.7 GB | — | Solo embeddings (no para chat) |

**💡 Recomendación:**
- **Uso diario:** `qwen2.5:7b` (rápido y fluido)
- **Análisis complejos:** `qwen2.5:72b` (más inteligente, pero lento)
- **Consultas ganadería:** `seedy:v16` (fine-tuned en el dominio)

---

## 🔧 Comandos Útiles

```bash
# Ver logs en tiempo real
docker compose logs -f

# Estado del servicio
docker compose ps

# Reiniciar
docker compose restart

# Parar
docker compose stop

# Arrancar de nuevo
docker compose start

# Parar y eliminar (conserva datos en volumen)
docker compose down

# Ver uso de recursos
docker stats open-webui-minipc
```

---

## 🔒 Autenticación (Opcional)

Si quieres activar login:

1. Editar `docker-compose.yml`:

```yaml
environment:
  - WEBUI_AUTH=True
  - WEBUI_SECRET_KEY=tu-clave-secreta-aqui
```

2. Reiniciar:

```bash
docker compose restart
```

3. Al acceder la primera vez, crea tu usuario administrador.

---

## 🐛 Troubleshooting

### Problema: No se conecta al DGX

**Síntomas:** Al abrir Open WebUI, no aparecen modelos o error de conexión.

**Solución:**

```bash
# 1. Verificar conectividad desde mini PC
curl http://192.168.20.57:11434/api/tags

# 2. Si falla, verificar firewall en DGX
ssh daviddgx@192.168.20.57
sudo ufw status
# Si está activo, permitir puerto 11434:
sudo ufw allow 11434/tcp

# 3. Verificar que Ollama está corriendo en DGX
docker ps | grep ollama

# 4. Verificar OLLAMA_HOST en DGX
docker exec ollama sh -c 'echo $OLLAMA_HOST'
# Debe ser: 0.0.0.0:11434
```

### Problema: Modelos muy lentos

**Causa:** El modelo `qwen2.5:72b` es naturalmente lento (4.3 tok/s en el DGX).

**Solución:** Usa `qwen2.5:7b` para chat interactivo. Reserva el 72B solo para análisis complejos.

### Problema: Open WebUI no arranca

```bash
# Ver logs de error
docker compose logs

# Verificar que el puerto 3000 no esté ocupado
sudo lsof -i :3000

# Recrear contenedor
docker compose down
docker compose up -d
```

---

## 📊 Métricas de Uso

| Recurso | Mini PC | DGX |
|---------|---------|-----|
| **RAM** | ~200 MB (Open WebUI) | 10-50 GB (modelos Ollama) |
| **CPU** | Mínimo (solo frontend) | Mínimo (GPU hace todo) |
| **GPU** | No usa | RTX 5080 16 GB VRAM |
| **Disco** | ~500 MB (imagen Docker + datos) | 60 GB (modelos) |
| **Red** | ~1-5 Mbps (API calls) | — |

---

## 💰 Coste

| Concepto | Coste |
|----------|-------|
| **Modelos locales (Ollama)** | $0 |
| **Open WebUI** | $0 |
| **APIs externas** | $0 |
| **Límites de uso** | Ninguno |
| **Total mensual** | **$0** |

vs. ChatGPT Plus: $20/mes  
vs. Claude Pro: $20/mes  
vs. Together.ai (uso medio): $40/mes

---

## 🔄 Actualizaciones

### Actualizar Open WebUI

```bash
cd ~/openwebui
docker compose pull
docker compose up -d
```

### Añadir nuevos modelos en el DGX

Los modelos se añaden en el DGX, no en el mini PC:

```bash
# Desde el DGX
ssh daviddgx@192.168.20.57

# Descargar modelo
docker exec ollama ollama pull nombre-del-modelo

# Automáticamente aparecerá en Open WebUI del mini PC
```

---

## 📚 Recursos

- **Open WebUI Docs:** https://docs.openwebui.com
- **Ollama Models:** https://ollama.com/library
- **Seedy GitHub:** https://github.com/karaokedurrif/Seedy

---

## ✅ Verificación Final

Checklist para confirmar que todo funciona:

- [ ] Open WebUI accesible en `http://192.168.20.54:3000`
- [ ] Lista de modelos aparece (qwen2.5:7b, qwen2.5:72b, seedy:v16)
- [ ] Puedes enviar un mensaje y recibir respuesta
- [ ] La respuesta llega en pocos segundos (con qwen2.5:7b)
- [ ] No hay errores en los logs

```bash
# Test rápido
curl -s http://192.168.20.54:3000/health
# Debe devolver: {"status":"ok"}
```

---

**Última actualización:** 5 mayo 2026  
**Versión:** 1.0  
**Autor:** Seedy Team
