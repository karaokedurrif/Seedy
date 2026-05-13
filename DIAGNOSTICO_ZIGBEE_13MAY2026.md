# Diagnóstico Zigbee — Dispositivos Desconectados (13 mayo 2026)

## 🔴 PROBLEMA

Dispositivos Zigbee aparecen **desconectados** en OvoSfera frontend:  
→ https://hub.ovosfera.com/farm/palacio/devices

Endpoint `/ovosfera/devices/status` muestra:
- Todos los sensores: `online: false`, `last_seen: null`
- Weather Ecowitt: ✅ funcionando (temp 9.9°C)

## 🔍 DIAGNÓSTICO

### Cadena de datos Zigbee

```
Mini PC (192.168.40.128)
  └─ Zigbee2MQTT (Docker :8080)
     └─ Dongle CH340/CC2652
        └─ MQTT Publish → zigbee2mqtt/{device}
           └─ Mosquitto Broker (DGX 192.168.20.57:1883)
              └─ Backend telemetry.py listener
                 └─ InfluxDB storage
                    └─ API /ovosfera/devices/status
                       └─ OvoSfera Frontend
```

### Punto de fallo identificado

**Mini PC Zigbee (192.168.40.128) NO RESPONDE al ping** ❌

```bash
$ ping -c 1 192.168.40.128
# Timeout - sin respuesta
```

### Verificaciones realizadas

1. **Backend DGX funcionando** ✅
   - seedy-backend UP
   - Edge events arriving (tracking pipeline activo)
   - Identity v4.2 funcionando (100% coverage)

2. **Mosquitto broker UP** ✅
   - Puerto 1883 accesible
   - Esperando mensajes en `zigbee2mqtt/#` → timeout (sin datos)

3. **Mini PC caído** ❌
   - 192.168.40.128 no responde
   - Zigbee2MQTT no puede publicar si el Mini PC está apagado

4. **Backend telemetry.py** ⚠️
   - Código existe: `backend/services/telemetry.py`
   - Importado en `main.py`: `start_mqtt_listener()`
   - **Sin logs de Telemetry** en backend (posible paho-mqtt no instalado)

5. **Weather Ecowitt funcionando** ✅
   - API Cloud v3 funciona independiente de Zigbee
   - MAC 88:57:21:17:AC:A7, temp 9.9°C

## 📋 SENSORES AFECTADOS

| Sensor | Tipo | Estado Actual | Última lectura |
|--------|------|---------------|----------------|
| gallinero_durrif_1 | eWeLink temp+hum | ❌ offline | null |
| gallinero_durrif_2 | eWeLink temp+hum | ❌ offline | null |
| sensor_tierra_gallineros | Tuya suelo | ❌ offline | null |
| sensor_aire_gallinero_grande | Tuya TS0601 | ❌ offline | null |
| sensor_aire_gallinero_pequeno | Tuya TS0601 | ❌ offline | null |
| **Ecowitt GW2000A** | **Meteo WiFi** | **✅ online** | **9.9°C** |

## 🔧 ACCIONES REQUERIDAS

### 1. Verificar físicamente el Mini PC

```bash
# Ubicación: 192.168.40.128
# Hardware: Mini PC Linux Mint 22.2
# Usuario: karaoke (sin contraseña guardada en memoria)
```

**Checklist físico:**
- [ ] Mini PC encendido?
- [ ] LEDs de red activos?
- [ ] Monitor/teclado conectado para ver estado?
- [ ] WiFi conectado? (nmcli device status)

### 2. Encender Mini PC (si está apagado)

```bash
# Acceso físico requerido
# O bien Wake-on-LAN si está configurado (no confirmado)
```

### 3. Verificar conectividad cuando esté UP

```bash
# Desde DGX o tu laptop
ping -c 5 192.168.40.128

# Si responde, conectar por SSH
ssh karaoke@192.168.40.128
```

### 4. Verificar Zigbee2MQTT en el Mini PC

```bash
# Dentro del Mini PC
docker ps | grep zigbee

# Debería mostrar:
# zigbee2mqtt   Up XX minutes   0.0.0.0:8080->8080/tcp

# Ver logs
docker logs --tail=50 zigbee2mqtt

# Verificar publicación MQTT
docker exec zigbee2mqtt cat /app/data/configuration.yaml | grep mqtt
```

### 5. Verificar WiFi Watchdog

```bash
# En el Mini PC
systemctl status wifi-watchdog

# Si está down, reiniciar
sudo systemctl restart wifi-watchdog

# Verificar que funciona
journalctl -u wifi-watchdog -f
```

### 6. Reiniciar Zigbee2MQTT (si está UP pero sin publicar)

```bash
# En el Mini PC
docker restart zigbee2mqtt

# Esperar 30s y verificar logs
docker logs --tail=100 -f zigbee2mqtt
```

### 7. Verificar paho-mqtt en backend DGX

```bash
# Desde DGX
cd /home/davidia/Documentos/Seedy
docker compose exec seedy-backend python -c "import paho.mqtt.client; print('OK')"

# Si falla, instalar
docker compose exec seedy-backend pip install paho-mqtt>=2.0

# Reiniciar backend para cargar el listener
docker compose restart seedy-backend

# Ver logs startup
docker compose logs --tail=100 -f seedy-backend | grep -i telemetry
```

### 8. Verificar mensajes MQTT llegando al broker

```bash
# Desde DGX
cd /home/davidia/Documentos/Seedy
docker compose exec -T mosquitto mosquitto_sub -h localhost -t 'zigbee2mqtt/#' -v

# Deberías ver mensajes cada pocos segundos:
# zigbee2mqtt/gallinero_durrif_1 {"temperature": 22.5, "humidity": 65, ...}
```

## ✅ VERIFICACIÓN FINAL

Después de encender el Mini PC y verificar la cadena:

```bash
# 1. Ejecutar script de diagnóstico
cd /home/davidia/Documentos/Seedy
bash diagnostico_zigbee_13mayo2026.sh

# 2. Verificar endpoint OvoSfera
curl -s localhost:8000/ovosfera/devices/status | python3 -m json.tool

# 3. Abrir frontend OvoSfera
# https://hub.ovosfera.com/farm/palacio/devices
# → Los sensores deberían aparecer ONLINE con datos actualizados
```

## 📊 MÉTRICAS ESPERADAS POST-FIX

| Métrica | Objetivo |
|---------|----------|
| Mini PC ping | < 5ms |
| Zigbee2MQTT UP | Yes |
| Mensajes MQTT/min | ~30 (5 sensores × 6 msg/min) |
| Backend logs Telemetry | "Conectado a MQTT broker" |
| Sensores online | 5/5 |
| Last_seen | < 60s |
| OvoSfera frontend | Temps actualizadas |

## 🔄 CONTINGENCIA

Si el Mini PC no puede ser reparado:

### Opción A: Migrar Zigbee2MQTT al DGX

```bash
# 1. Mover dongle USB al DGX
# 2. Modificar docker-compose.yml para añadir zigbee2mqtt
# 3. Mapear device /dev/ttyUSB0 o /dev/ttyACM0
# 4. Configurar Z2M para usar MQTT local (mosquitto:1883)
```

### Opción B: Usar backup Mini PC (si existe)

```bash
# Configurar otro Mini PC con la misma IP 192.168.40.128
# Instalar Docker + Zigbee2MQTT
# Conectar dongle CC2652
# Copiar configuración Zigbee2MQTT
```

## 📝 HISTORIAL

- **13 mayo 2026 10:35 UTC**: Diagnóstico inicial
  - Mini PC 192.168.40.128 no responde
  - Todos los sensores Zigbee offline
  - Weather Ecowitt funciona independiente
  - Backend logs sin Telemetry/MQTT

## 🔗 REFERENCIAS

- `/memories/seedy-zigbee-troubleshooting.md` (crear después del fix)
- `backend/services/telemetry.py`: Listener MQTT
- `backend/routers/devices.py`: API `/ovosfera/devices/status`
- Zigbee2MQTT docs: https://www.zigbee2mqtt.io/
- Mini PC WiFi watchdog: `DUAL_WIFI_SETUP_STATUS.md`

---

**ESTADO**: 🔴 Esperando acceso físico al Mini PC para verificar hardware  
**PRIORIDAD**: ALTA (sensores IoT críticos para monitoreo gallineros)  
**ETA FIX**: Inmediato tras encender Mini PC (< 5 min)
