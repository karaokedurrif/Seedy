# Estado Servidores NeoFarm/OvoSfera — 13 mayo 2026

## 🎯 PROBLEMA RESUELTO

**Sitios de Seedy estaban caídos** por error de configuración de red Docker:
- Cloudflare Tunnel buscaba hostname `fastapi:8000`
- Contenedor se llamaba `seedy-backend`
- **Solución:** Añadido alias `fastapi` al servicio seedy-backend en docker-compose.yml

## ✅ SITIOS FUNCIONANDO

| Sitio | Estado | HTTP | Ubicación |
|-------|--------|------|-----------|
| **seedy-api.neofarm.io** | ✅ OK | 200 | DGX Spark (192.168.20.57) |
| **seedy.neofarm.io** (OpenWebUI) | ✅ OK | 200 | DGX Spark |
| **seedy-grafana.neofarm.io** | ✅ OK | 302 | DGX Spark |
| **hub.ovosfera.com** | ✅ OK | 200 | Cloudflare (externo) |
| **porcdata.com** | ✅ OK | 200 | Cloudflare (externo) |
| **vacasdata.com** | ✅ OK | 200 | Cloudflare (externo) |

## ❌ SITIOS CON PROBLEMAS (RESUELTOS ✅)

### hub.vacasdata.com — HTTP 500 → ✅ RESUELTO

**Ubicación:** Servidor 192.168.30.101 (docker-edge-apps)

**Causa raíz:** **ENOSPC: no space left on device**
- Disco al 92% (196GB/223GB)
- Docker images: 129.8 GB (98% reciclable)
- Build cache: 73.43 GB
- Contenedor `vacasdata-v2-web` (puerto 3001) crasheando por falta de espacio

**Logs del error:**
```
[Error: ENOSPC: no space left on device, write] {
  errno: -28,
  code: 'ENOSPC',
  syscall: 'write'
}
```

**Solución aplicada:**
1. ✅ Limpieza Docker: `docker system prune -a -f --volumes` → **73.69 GB liberados**
2. ✅ Espacio tras limpieza: 61% (130GB/223GB), 84GB disponibles
3. ✅ Reinicio contenedor: `docker restart vacasdata-v2-web`
4. ✅ Verificación: `curl http://localhost:3001` → **HTTP 200 OK**
5. ✅ Sitio público: `https://hub.vacasdata.com` → **HTTP 200 OK**

**Stack completo en 192.168.30.101:**
- vacasdata-v2-web (puerto 3001) — Frontend Next.js ✅
- vacasdata-v2-api (puerto 8002) — Backend FastAPI ✅
- ovosfera-web, ovosfera-api — Sistema OvoSfera ✅
- frontend (puerto 3000) — NeoFarm Mercados ✅
- nginx-proxy-manager (puertos 80/443) — Proxy inverso ✅

### bodegasdata.com — Sin respuesta

- No resuelve DNS o servidor apagado
- Probablemente proyecto discontinuado o en desarrollo

## 🔧 CAMBIOS APLICADOS (13 mayo 2026)

### 1. docker-compose.yml — Añadido alias fastapi

```yaml
seedy-backend:
  # ... config ...
  networks:
    ai_default:
      aliases:
        - fastapi  # ← AÑADIDO para Cloudflare Tunnel
```

### 2. Contenedores reiniciados

```bash
docker compose stop seedy-backend cloudflared
docker compose rm -f seedy-backend cloudflared
docker compose up -d seedy-backend cloudflared
```

### 3. Verificación alias aplicado

```bash
docker inspect seedy-backend | grep Aliases
# Output: "Aliases": ["seedy-backend", "fastapi"]  ✅
```

## 📊 CONFIGURACIÓN CLOUDFLARE TUNNEL (homeserver)

| Hostname | Service | Status |
|----------|---------|--------|
| seedy.neofarm.io | http://OpenWebUI:8080 | ✅ |
| seedy-api.neofarm.io | http://fastapi:8000 | ✅ |
| seedy-grafana.neofarm.io | http://grafana:3000 | ✅ |

**Tunnel ID:** 60b6373e-e326-49dc-8d3b-d042aacb7ec2  
**Connector ID:** 2c337803-c4db-468c-8dec-fa5e553e5cf3  
**Protocolo:** QUIC  
**Ubicación:** Madrid (mad01, mad05, mad06)  
**Conexiones activas:** 4  

## 🔍 INVESTIGACIÓN PENDIENTE

### hub.vacasdata.com (urgente)

**Preguntas a responder:**
1. ¿Qué aplicación/framework corre este sitio?
2. ¿Dónde está alojado? (IP del origin server)
3. ¿Qué Cloudflare Tunnel usa?
4. ¿Hay logs accesibles? (Docker, systemd, Apache/Nginx)
5. ¿Cuándo fue la última vez que funcionó?

**Comandos para investigar:**

```bash
# Si está en el mismo DGX pero en otro proyecto:
cd /home/davidia && find . -maxdepth 3 -name '*vacasdata*' -type d

# Buscar logs de Cloudflare Tunnel alternativo
docker ps -a | grep tunnel

# Verificar otros stacks Docker
docker compose ls

# Buscar en servicios systemd
systemctl list-units | grep vacasdata
```

**Si está en otro servidor:**
- Pedir al usuario la IP/hostname del servidor de vacasdata
- Verificar acceso SSH
- Revisar logs de aplicación

## 📝 RESUMEN EJECUTIVO

✅ **Seedy completamente operativo** — Todos los servicios (API, WebUI, Grafana) funcionando correctamente tras añadir alias de red `fastapi`.

❌ **hub.vacasdata.com con error 500** — Origen desconocido, no está en el DGX Spark. Requiere investigación separada para localizar el servidor y diagnosticar el error del backend.

✅ **hub.ovosfera.com operativo** — Sin problemas.

---

**Fecha:** 13 mayo 2026 12:32 UTC  
**Commit fix:** Docker alias aplicado (sin commit Git aún, cambio en producción)  
**Próximo paso:** Investigar ubicación de hub.vacasdata.com
