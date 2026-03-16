# Tailscale — Setup para Seedy (MSI Vector 16 HX)

> **Objetivo**: Acceso remoto seguro a Open WebUI, Seedy API, Grafana y Qdrant  
> **Máquina**: MSI Vector 16 HX, Ubuntu 24.04, red local 192.168.30.x

---

## 1. Instalar Tailscale

```bash
# Añadir repo oficial
curl -fsSL https://tailscale.com/install.sh | sh

# Iniciar y autenticar
sudo tailscale up

# (Se abrirá un enlace para autenticar en https://login.tailscale.com)
```

## 2. Verificar conexión

```bash
# Ver IP de Tailscale asignada
tailscale ip -4
# Ejemplo: 100.x.y.z

# Estado completo
tailscale status
```

## 3. Habilitar como Exit Node (opcional)

Solo si quieres rutear TODO el tráfico de otros dispositivos a través de esta máquina:

```bash
# Habilitar exit node + subnet router
sudo tailscale up --advertise-exit-node --advertise-routes=192.168.30.0/24

# En la consola web de Tailscale (admin), aprobar:
#   - Exit node
#   - Subnet route 192.168.30.0/24
```

## 4. Acceder a los servicios

Con Tailscale activo en cualquier dispositivo (móvil, portátil, tablet):

| Servicio | URL Tailscale |
|---|---|
| **Open WebUI** | `http://<tailscale-ip>:3000` |
| **Seedy API** | `http://<tailscale-ip>:8000/docs` |
| **Qdrant Dashboard** | `http://<tailscale-ip>:6333/dashboard` |
| **Grafana** | `http://<tailscale-ip>:3001` |
| **Node-RED** | `http://<tailscale-ip>:1880` |
| **InfluxDB** | `http://<tailscale-ip>:8086` |

### Alternativa: MagicDNS

Si tienes MagicDNS habilitado en Tailscale:
```
http://davidia-vector.tail12345.ts.net:3000
```
(El nombre exacto aparece en `tailscale status`)

## 5. Compartir con otros usuarios (opcional)

```bash
# Desde la consola web de Tailscale:
# Settings → Sharing → Share machine → invitar por email
# O usar Tailscale Funnel para exponer un solo puerto a internet:
sudo tailscale funnel 3000
# Crea una URL pública tipo https://davidia-vector.tail12345.ts.net/
```

## 6. Firewall — Tailscale ACLs

En la consola de Tailscale (admin), configura ACLs para limitar acceso:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["autogroup:admin"],
      "dst": ["*:*"]
    },
    {
      "action": "accept", 
      "src": ["autogroup:member"],
      "dst": ["*:3000", "*:8000"]
    }
  ]
}
```

Esto permite:
- Admins (tú): acceso total
- Miembros invitados: solo Open WebUI y Seedy API

## 7. Auto-start en boot

Tailscale se instala como servicio systemd por defecto:

```bash
# Verificar que arranca con el sistema
sudo systemctl is-enabled tailscaled
# Debe decir: enabled

# Si no:
sudo systemctl enable tailscaled
```

## 8. Verificar que todo funciona

```bash
# Desde otro dispositivo con Tailscale:
curl -s http://<tailscale-ip>:8000/health
# Debe devolver: {"status": "ok"}

curl -s http://<tailscale-ip>:6333/healthz
# Debe devolver: ok

curl -s http://<tailscale-ip>:11434/api/tags | python3 -m json.tool | head -5
# Debe listar los modelos de Ollama
```

---

## Notas

- Tailscale es **gratuito** para uso personal (hasta 100 dispositivos)
- El tráfico va cifrado WireGuard punto a punto (no pasa por servidores de Tailscale)
- Latencia típica: <5ms en red local, <50ms remoto
- No requiere abrir puertos en el router ni configurar DDNS
- Compatible con NAS (OMV tiene plugin de Tailscale)
