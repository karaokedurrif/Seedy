# 🔗 INTEGRACIÓN DGX → MINI PC → BEBOP

## ARQUITECTURA COMPLETA

```
┌─────────────────────────────────────────────────────────────────┐
│                    FLUJO DE DETECCIÓN → VUELO                    │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  DGX Server  │  WiFi   │   Mini PC    │  WiFi   │ Parrot Bebop │
│ 192.168.20.57│  5G     │ 192.168.20.X │  Direct │ 192.168.42.1 │
│              │◄───────►│              │◄───────►│              │
│ - YOLO Pest  │         │ - 2× WiFi    │         │ - Olympe SDK │
│ - Seedy API  │         │ - drone_     │         │ - Vuelo 2m   │
│ - Detection  │         │   bridge.py  │         │ - 10s hover  │
└──────────────┘         └──────────────┘         └──────────────┘
       │                        │                        │
       │ 1. Detecta gorriones   │                        │
       │    (≥3 aves, >10s)     │                        │
       │                        │                        │
       ├─────────────────────────►2. POST /api/dron/    │
       │   sparrow-deterrent     │    sparrow-deterrent  │
       │                        │                        │
       │                        ├─────────────────────────►3. Vuelo
       │                        │    POST /fly           │    ejecutado
       │                        │                        │
       │                        │◄─────────────────────────4. Status
       │◄────────────────────────5. Resultado           │
       │                        │                        │
```

## 📋 CONFIGURACIÓN EN 3 PASOS

### 1️⃣ MINI PC: Configurar Dual WiFi

**En el mini PC (karaoke@192.168.40.128):**

```bash
# Copiar archivos desde laptop
scp setup_dual_wifi_auto.sh drone_bridge.py fly_bebop_10s.sh karaoke@192.168.40.128:~

# Ejecutar configuración
ssh karaoke@192.168.40.128
chmod +x setup_dual_wifi_auto.sh
./setup_dual_wifi_auto.sh
```

**Resultado esperado:**
```
✅ CONFIGURACIÓN DUAL WiFi COMPLETADA

Estado final:
  • D-Link (wlx00265a1686dc): 192.168.20.X → DGX + Internet
  • Atheros (wlxc01c30430fbc): 192.168.42.X → Bebop
```

**IP del mini PC en red DGX:** Se mostrará al final del script (ej: `192.168.20.45`)

### 2️⃣ MINI PC: Iniciar drone_bridge.py

```bash
cd /home/karaoke
nohup python3 drone_bridge.py > drone_bridge.log 2>&1 &

# Verificar que corre
ps aux | grep drone_bridge
curl http://localhost:9090/health
```

### 3️⃣ DGX: Configurar URL del Mini PC

**En el backend de Seedy (DGX):**

Editar `/backend/.env` o configurar variable de entorno:

```bash
DRONE_BRIDGE_URL=http://192.168.20.45:9090
```

Donde `192.168.20.45` es la IP del mini PC obtenida en el paso 1.

**Reiniciar backend si es necesario:**

```bash
docker compose restart seedy-backend
```

## 🚀 USO DESDE EL DGX

### Opción A: Via API de Seedy (Recomendado)

El backend de Seedy ya tiene integración con el dron:

```bash
# Desde cualquier lugar que pueda acceder al backend
curl -X POST http://localhost:8000/api/dron/sparrow-deterrent
```

**Respuesta esperada:**

```json
{
  "status": "completed",
  "timestamp": 1715547890.5,
  "datetime": "2026-05-12T20:25:30",
  "duration_s": 22.3,
  "reason": ""
}
```

### Opción B: Directo al Mini PC (Avanzado)

```bash
# Conectar al dron primero
curl -X POST http://192.168.20.45:9090/connect

# Lanzar vuelo
curl -X POST http://192.168.20.45:9090/fly

# Ver estado
curl http://192.168.20.45:9090/status
```

### Opción C: Integración con YOLO Pest Detection

En el código de detección de plagas del DGX:

```python
import httpx

async def on_sparrows_detected(count: int, camera: str):
    """Callback cuando YOLO detecta gorriones persistentes."""
    if count >= 3:
        # Enviar comando al backend de Seedy
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:8000/api/dron/sparrow-deterrent",
                timeout=60.0
            )
            result = resp.json()
            print(f"🚁 Dron desplegado: {result}")
```

## 📊 ENDPOINTS DISPONIBLES

### Backend Seedy (DGX - Puerto 8000)

| Endpoint | Método | Función |
|----------|--------|---------|
| `/api/dron/status` | GET | Estado del dron (conectado, volando, cooldown, etc.) |
| `/api/dron/connect` | POST | Conectar al Bebop vía bridge |
| `/api/dron/disconnect` | POST | Desconectar |
| `/api/dron/sparrow-deterrent` | POST | **Lanzar vuelo anti-gorriones** |
| `/api/dron/flight-log` | GET | Historial de vuelos (últimos 50) |

### Mini PC Bridge (Puerto 9090)

| Endpoint | Método | Función |
|----------|--------|---------|
| `/health` | GET | Health check del bridge |
| `/status` | GET | Estado dron (conectado, volando) |
| `/connect` | POST | Conectar vía Olympe SDK |
| `/fly` | POST | **Ejecutar vuelo** (2m, 10s hover) |

## 🛡️ REGLAS DE SEGURIDAD

El sistema tiene límites de seguridad configurados:

```python
SAFETY = {
    "max_flights_per_hour": 5,        # Máximo 5 vuelos/hora
    "max_flights_per_day": 20,        # Máximo 20 vuelos/día
    "no_fly_hours": (22, 7),          # No volar 22:00-07:00
    "min_battery_pct": 30,            # Batería mínima 30%
    "max_wind_speed_kmh": 25,         # Viento máximo 25 km/h
    "cooldown_s": 120,                # 2 min entre vuelos
}
```

Si el sistema rechaza un vuelo, la respuesta incluirá el motivo:

```json
{
  "status": "skipped",
  "reason": "cooldown_45s"  // O "no_fly_hours_22-7", "max_flights_per_hour", etc.
}
```

## 🧪 PRUEBAS

### Test 1: Conectividad Mini PC desde DGX

```bash
# Desde el DGX
ping -c 2 192.168.20.45  # IP del mini PC en red 5G
curl http://192.168.20.45:9090/health
```

**Esperado:** `{"status": "healthy", "connected": false, "is_flying": false}`

### Test 2: Vuelo de prueba

```bash
# Desde el DGX
curl -X POST http://localhost:8000/api/dron/sparrow-deterrent
```

**Esperado:** El Bebop debe despegar, subir 2m, hacer hover 10s, y aterrizar suavemente.

### Test 3: Ver historial

```bash
curl http://localhost:8000/api/dron/flight-log
```

**Esperado:** JSON con lista de vuelos realizados.

### Test 4: Estado del sistema

```bash
curl http://localhost:8000/api/dron/status
```

**Esperado:**
```json
{
  "connected": true,
  "is_flying": false,
  "can_fly": true,
  "reason": "ready",
  "cooldown_remaining": 0,
  "flights_last_hour": 1,
  "flights_today": 3,
  ...
}
```

## 🔧 TROUBLESHOOTING

### Error: "Bridge no disponible"

**Causa:** El DGX no puede acceder al mini PC en la red 5G.

**Solución:**
1. Verificar que el mini PC esté en la red 5G: `ssh karaoke@192.168.40.128 "ip addr show | grep 192.168.20"`
2. Verificar conectividad: `ping 192.168.20.45` (desde el DGX)
3. Verificar que drone_bridge.py esté corriendo: `ssh karaoke@192.168.40.128 "ps aux | grep drone_bridge"`
4. Revisar firewall del mini PC: `sudo ufw status` (debe permitir puerto 9090)

### Error: "Dron no responde"

**Causa:** El mini PC está conectado a la red 5G pero no al Bebop.

**Solución:**
```bash
# En el mini PC
sudo nmcli connection up Bebop2-045265
ping 192.168.42.1  # Debe responder
```

### Error: "cooldown_XXs"

**Causa:** Límite de seguridad, demasiados vuelos recientes.

**Solución:** Esperar el cooldown indicado (default 120s). Para emergencias, editar `SAFETY["cooldown_s"]` en `sparrow_deterrent.py` y reiniciar backend.

### Error: "no_fly_hours_22-7"

**Causa:** Horario nocturno (22:00-07:00).

**Solución:** Esperar a las 07:00, o modificar `SAFETY["no_fly_hours"]` si es necesario (ej. demo diurna).

## 📝 LOGS ÚTILES

### Mini PC

```bash
# Log del bridge
ssh karaoke@192.168.40.128 "tail -f ~/drone_bridge.log"

# Conexiones WiFi activas
ssh karaoke@192.168.40.128 "nmcli connection show --active"

# Rutas
ssh karaoke@192.168.40.128 "ip route show"
```

### DGX (Seedy Backend)

```bash
# Logs del backend
docker compose logs -f seedy-backend | grep "🚁"

# Últimos eventos del dron
docker compose exec mosquitto mosquitto_sub -h localhost -t "seedy/dron/#" -v
```

## 🎯 FLUJO COMPLETO AUTOMÁTICO

Para automatizar completamente la detección → vuelo:

```python
# En el código de pest detection del DGX (pest_alert.py)

from services.sparrow_deterrent import get_deterrent

async def on_pest_detected(pest_type: str, count: int, camera_id: str):
    """Callback desde el loop de visión."""
    if pest_type == "gorrion" and count >= 3:
        # El deterrent ya tiene check_sparrow_trigger()
        # que maneja automáticamente triggers y cooldowns
        deterrent = get_deterrent()
        triggered = deterrent.check_sparrow_trigger(
            detections=[...],  # Lista de detecciones YOLO
            camera_id=camera_id
        )
        if triggered:
            logger.info(f"🚁 Dron desplegado automáticamente contra gorriones")
```

El sistema ya tiene todo integrado. Solo necesitas:
1. Configurar dual WiFi en el mini PC
2. Iniciar drone_bridge.py
3. Configurar DRONE_BRIDGE_URL en el DGX

---

**Fecha:** 12 mayo 2026  
**DGX:** 192.168.20.57  
**Mini PC:** 192.168.20.X (asignado por DHCP en red 5G)  
**Bebop:** 192.168.42.1  
