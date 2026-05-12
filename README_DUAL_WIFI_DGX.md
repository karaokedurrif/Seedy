# 🚁 CONFIGURACIÓN DUAL WiFi PARA INTEGRACIÓN DGX → BEBOP

## ✅ SOLUCIÓN: Dual WiFi en Mini PC

**Problema:** El mini PC pierde acceso remoto cuando se conecta al Bebop.

**Solución:** Usar 2 adaptadores WiFi simultáneamente:
- **D-Link DWA-140** → Casa_HS_Wifi 5G (red DGX 192.168.20.x, default route)
- **Atheros AR9271** → Bebop2-045265 (red dron 192.168.42.x, never-default)

## 📋 EJECUCIÓN EN EL MINI PC

### 1️⃣ Copiar archivos al mini PC

Desde tu laptop (cuando el mini PC esté accesible):

```bash
cd /home/davidia/Documentos/Seedy
scp setup_dual_wifi_auto.sh drone_bridge.py fly_bebop_10s.sh karaoke@192.168.40.128:~
```

### 2️⃣ Ejecutar en el mini PC

Conéctate al mini PC:

```bash
ssh karaoke@192.168.40.128
```

Ejecuta el script de configuración:

```bash
chmod +x setup_dual_wifi_auto.sh
./setup_dual_wifi_auto.sh
```

El script hará:
- ✅ Detectar las 2 interfaces WiFi (D-Link + Atheros)
- ✅ Conectar D-Link a Casa_HS_Wifi 5G (con contraseña incluida)
- ✅ Configurar Atheros para Bebop (never-default)
- ✅ Conectar ambas simultáneamente
- ✅ Verificar conectividad DGX + Bebop

**Duración:** ~30 segundos

### 3️⃣ Iniciar drone_bridge.py

```bash
cd /home/karaoke
nohup python3 drone_bridge.py > drone_bridge.log 2>&1 &
```

### 4️⃣ Test de vuelo

```bash
./fly_bebop_10s.sh
```

## 🎯 RESULTADO ESPERADO

Después de ejecutar `setup_dual_wifi_auto.sh`:

```
Estado final:
  • D-Link (wlx00265a1686dc): 192.168.20.X → DGX + Internet
  • Atheros (wlxc01c30430fbc): 192.168.42.X → Bebop

El mini PC ahora tiene acceso simultáneo a:
  1. DGX en 192.168.20.57 (vía D-Link)
  2. Bebop en 192.168.42.1 (vía Atheros)
  3. Internet (vía D-Link, default route)
```

## 🔗 INTEGRACIÓN CON DGX

Una vez configurado, el DGX puede enviar comandos de vuelo al mini PC:

```bash
# Desde el DGX (192.168.20.57):
curl -X POST http://192.168.20.X:9090/fly
```

Donde `192.168.20.X` es la IP que el mini PC obtenga en la red 5G.

El script `setup_dual_wifi_auto.sh` te mostrará esta IP al final.

## 🛠️ TROUBLESHOOTING

### Si el D-Link no se detecta:

```bash
# Verificar USB:
lsusb | grep -i "d-link\|07d1:3c0a"

# Debería aparecer:
# Bus 001 Device 003: ID 07d1:3c0a D-Link System DWA-140

# Si no aparece, desconecta y reconecta el USB
```

### Si Casa_HS_Wifi 5G no conecta:

Verifica que la contraseña sea correcta: `ErizoDespenado22`

Edita el script si cambió:

```bash
nano setup_dual_wifi_auto.sh
# Busca: WIFI_5G_PASS="ErizoDespenado22"
```

### Si Bebop no conecta:

1. Verifica que el Bebop esté encendido (LEDs verdes)
2. Verifica que el SSID sea "Bebop2-045265"
3. Conéctate manualmente:

```bash
sudo nmcli device wifi connect "Bebop2-045265" ifname wlxc01c30430fbc
```

### Para reconectar Bebop en el futuro:

```bash
sudo nmcli connection up Bebop2-045265
```

### Para ver el log del drone_bridge:

```bash
tail -f ~/drone_bridge.log
```

## 📊 VERIFICACIÓN DE ESTADO

```bash
# Ver conexiones activas:
nmcli connection show --active

# Ver rutas:
ip route show

# Ver IPs:
ip addr show | grep "inet " | grep "192.168"

# Test DGX:
ping -c 2 192.168.20.57

# Test Bebop:
ping -c 2 192.168.42.1

# Test drone bridge:
curl http://localhost:9090/health
```

## 🚀 PARÁMETROS DE VUELO ACTUALES

El vuelo configurado en `fly_bebop_10s.sh` y `drone_bridge.py`:

- **Altura:** 2 metros
- **Hover:** 10 segundos
- **Descenso:** Lento en 2 pasos (1m → 0.5m → suelo)
- **Duración total:** ~20-25 segundos

## 📝 ARCHIVOS

- `setup_dual_wifi_auto.sh` - Configuración automatizada dual WiFi (12KB)
- `drone_bridge.py` - HTTP server para Olympe SDK (4.5KB)
- `fly_bebop_10s.sh` - Script de vuelo completo (4KB)
- `configure_dual_wifi_dgx.sh` - Versión interactiva (9.7KB, backup)
- `README_DUAL_WIFI_DGX.md` - Este archivo

---

**Fecha:** 12 mayo 2026  
**WiFi 5G:** Casa_HS_Wifi 5G (ErizoDespenado22)  
**Mini PC:** karaoke@192.168.40.128 (password: 1234)
