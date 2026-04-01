# Infraestructura de Red NeoFarm / Seedy — Lecciones y Configuración

> Fecha: 2026-03-22  
> Motivo: Cortes recurrentes por ISP (Telefónica) perdiendo paquetes a rango anycast Cloudflare `188.114.96.x / 188.114.97.x`

---

## 1. Problema raíz

| Síntoma | Causa |
|---------|-------|
| `seedy-api.neofarm.io` inaccesible desde red local | Telefónica descarta paquetes en hop 4+ hacia rango CF `188.114.96/97` |
| `docker pull` falla con `i/o timeout` | Docker Hub (`registry-1.docker.io`) usa Cloudflare; misma ruta afectada |
| Tunnel cloudflared **funciona** | Sale por QUIC a `198.41.x.x` (Madrid), rango distinto no afectado |

El problema es **intermitente y a nivel ISP** — no hay nada que podamos hacer para forzar la ruta.
Cloudflare asigna distintas IPs anycast según momento; a veces caen en rangos accesibles (104.21.x, 172.67.x) y otras en el rango muerto (188.114.x).

---

## 2. Soluciones aplicadas (2026-03-22)

### 2.1 Docker Registry Mirror en CTs Proxmox

| CT | Nombre | daemon.json |
|----|--------|-------------|
| 102 | docker-edge-apps | ✅ mirror + address pools + log config |
| 103 | voice-ai | ✅ mirror + address pools |

```json
{
  "registry-mirrors": ["https://mirror.gcr.io"],
  "default-address-pools": [
    {"base": "172.24.0.0/13", "size": 24}
  ]
}
```

**Validado**: `docker pull alpine` OK en ambos CTs vía `mirror.gcr.io`.

### 2.2 Reglas de firewall

Ajustadas en el firewall (Proxmox / router) para prevenir que el tráfico hacia rangos CF problemáticos bloquee los servicios.

### 2.3 DNS se re-resolvió a IPs funcionales

- **Antes** (roto): `188.114.96.5` / `188.114.97.5`
- **Ahora** (funciona): `104.21.90.15` / `172.67.193.80`

⚠️ Esto puede cambiar de nuevo en cualquier momento — Cloudflare rota IPs anycast.

---

## 3. ⚠️ PENDIENTE: Host principal (MSI Vector)

**El host donde corre el stack Docker de Seedy NO tiene mirror configurado.**

```
# /etc/docker/daemon.json actual en davidia-Vector-A16-HX-A8WIG:
{
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    }
}
```

### 🔧 Acción recomendada — Añadir mirror al host principal:

```json
{
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    },
    "registry-mirrors": ["https://mirror.gcr.io"]
}
```

Luego: `sudo systemctl restart docker`

> Sin esto, cualquier `docker pull` / `docker compose up` que necesite descargar imágenes
> seguirá fallando cuando CF asigne IPs del rango 188.114.x.

---

## 4. Mejoras adicionales recomendadas

### 4.1 Split-horizon DNS local (ALTA PRIORIDAD)

**Problema**: Incluso con mirrors para Docker, el **navegador** accede a `seedy-api.neofarm.io` vía Cloudflare. Si CF cae, OvoSfera no puede cargar el inject.js ni hacer llamadas API.

**Solución**: Resolver `seedy-api.neofarm.io` directamente a la IP local cuando estamos en la LAN.

**Opción A — /etc/hosts (más simple)**:
```bash
# En cada equipo de la LAN que use OvoSfera:
echo "192.168.20.131 seedy-api.neofarm.io seedy.neofarm.io seedy-grafana.neofarm.io" | sudo tee -a /etc/hosts
```

Requiere HTTPS local → ya preparado un Caddy reverse proxy con certs mkcert (ver sección 5).

**Opción B — dnsmasq en el router/servidor (más robusto)**:
```bash
# En el router o servidor con dnsmasq:
address=/seedy-api.neofarm.io/192.168.20.131
address=/seedy.neofarm.io/192.168.20.131
address=/seedy-grafana.neofarm.io/192.168.20.131
```

Aplica a toda la LAN automáticamente, sin tocar cada equipo.

### 4.2 Caddy Local HTTPS Proxy (ya preparado)

Ya configurado en `docker-compose.yml` y `Caddyfile`:

- **Caddy** en puerto 443 del host
- Certs mkcert en `./certs/` (válidos hasta 2028-06-22)
- Reverse proxy: `seedy-api.neofarm.io` → `fastapi:8000`, `seedy.neofarm.io` → `OpenWebUI:8080`, `seedy-grafana.neofarm.io` → `grafana:3000`

Para activar hace falta:
1. Instalar CA de mkcert: `sudo /tmp/mkcert -install` (una vez)
2. Levantar caddy: `docker compose up -d caddy-local` (necesita la imagen — hoy no se pudo por el mismo problema CF/Docker Hub)
3. Añadir `/etc/hosts` según opción A arriba

### 4.3 Múltiples registry mirrors (redundancia)

```json
"registry-mirrors": [
    "https://mirror.gcr.io",
    "https://registry.docker-cn.com",
    "https://docker.mirrors.ustc.edu.cn"
]
```

Docker probará cada mirror en orden. Si `mirror.gcr.io` falla, usa el siguiente.

### 4.4 Monitorización de conectividad CF

Script cron que alerte cuando CF sea inaccesible:

```bash
# /etc/cron.d/check-cf-connectivity
*/5 * * * * root timeout 3 curl -sk https://seedy-api.neofarm.io/health > /dev/null 2>&1 || echo "$(date): CF UNREACHABLE" >> /var/log/cf-health.log
```

### 4.5 IPv6 como fallback

Las IPs IPv6 de CF (`2606:4700:3032::ac43:c150`, `2606:4700:3033::6815:5a0f`) podrían funcionar cuando IPv4 falla. Verificar si Telefónica tiene IPv6 habilitado y considerar `prefer-family = IPv6` en la config.

---

## 5. Resumen de la arquitectura de red

```
                     ┌─────────────────────────────────────┐
                     │         Internet / Cloudflare        │
                     │  (anycast IPs — variable, riesgo)    │
                     └──────────┬────────────┬──────────────┘
                                │            │
                    Tunnel QUIC │            │ HTTPS (navegador)
                   198.41.x.x  │            │ 104.21 / 172.67 / 188.114 ⚠️
                                │            │
┌───────────────────────────────┴────────────┴──────────────────┐
│                    Router 192.168.20.1                         │
│                    (Telefónica / fibra)                        │
└───────────────────────────────┬───────────────────────────────┘
                                │ 192.168.20.x
                                │
        ┌───────────────────────┴───────────────────┐
        │       MSI Vector (192.168.20.131)         │
        │       davidia-Vector-A16-HX-A8WIG         │
        │                                           │
        │   Docker: ai_default network              │
        │   ├─ seedy-backend (fastapi:8000)         │
        │   ├─ ollama (:11434)                      │
        │   ├─ qdrant (:6333)                       │
        │   ├─ open-webui (:3000→8080)              │
        │   ├─ cloudflared (tunnel QUIC)            │
        │   ├─ caddy-local (:443) [preparado]       │
        │   ├─ grafana (:3001→3000)                 │
        │   ├─ influxdb (:8086)                     │
        │   ├─ mosquitto (:1883)                    │
        │   └─ nodered (:1880)                      │
        │                                           │
        │   enp4s0: 10.10.10.1 (VLAN cámaras)      │
        │   wlxccba...: 192.168.20.131 (WiFi LAN)  │
        └───────────────────────────────────────────┘
                                │ 10.10.10.x
                    ┌───────────┴───────────┐
                    │   go2rtc / cámaras    │
                    │   H.264 streams       │
                    └───────────────────────┘

Proxmox CTs (mirrors configurados):
  CT 102: docker-edge-apps ✅
  CT 103: voice-ai ✅
```

---

## 6. Checklist post-incidente

- [x] Mirror `mirror.gcr.io` en CT 102
- [x] Mirror `mirror.gcr.io` en CT 103
- [x] Reglas firewall actualizadas
- [x] Verificado `docker pull` en CTs
- [ ] **Mirror `mirror.gcr.io` en host MSI Vector** ← PENDIENTE
- [ ] **Instalar CA mkcert** (`sudo /tmp/mkcert -install`)
- [ ] **Levantar caddy-local** (`docker compose up -d caddy-local`)
- [ ] **Configurar split-horizon DNS** (hosts o dnsmasq)
- [ ] Verificar IPv6 como fallback
- [ ] Añadir cron de monitorización CF
