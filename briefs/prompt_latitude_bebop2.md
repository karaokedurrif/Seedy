# Prompt: Conectar Parrot Bebop 2 via Atheros USB Dongle + Lanzar Drone Bridge

**Máquina:** Dell Latitude · Linux Mint · IP LAN `192.168.20.102`
**Dongle:** Atheros AR9271 · Interfaz: `wlxc01c30430fbc`
**Dron:** Parrot Bebop 2 · Red WiFi: `BebopDrone-XXXXX` · IP dron: `192.168.42.1`
**Destino:** El bridge HTTP escuchará en `0.0.0.0:9090` para que Seedy (MSI en `192.168.20.131`) lo llame.

---

## PASO 1: Verificar el dongle

```bash
# Confirmar que el kernel lo ve
ip link show wlxc01c30430fbc
# Debe salir con state UP o DOWN — cualquiera está bien

# Si no aparece:
lsusb | grep -i atheros
# Debe salir: "Qualcomm Atheros Communications AR9271"
```

## PASO 2: Encender el Bebop 2

Enciende el dron manualmente (botón power 3 segundos). Espera 30 segundos a que cree su red WiFi.

## PASO 3: Escanear y conectar al Bebop

```bash
# Escanear redes visibles desde el dongle
sudo iwlist wlxc01c30430fbc scan 2>/dev/null | grep -i "ESSID"
# Buscar: BebopDrone-EXXXXXX (red abierta, sin password)

# Conectar el dongle a la red del Bebop
# Reemplaza BebopDrone-EXXXXXX con el ESSID real
nmcli device wifi connect "BebopDrone-EXXXXXX" ifname wlxc01c30430fbc

# Verificar IP asignada (debe ser 192.168.42.x)
ip addr show wlxc01c30430fbc | grep "inet "

# Ping al dron
ping -c 3 192.168.42.1
```

**IMPORTANTE:** La conexión LAN principal del Latitude (ethernet o WiFi interna) debe seguir activa. El dongle solo se conecta al Bebop; el resto del tráfico va por la interfaz principal. Verifica:

```bash
# Debe haber DOS rutas: una LAN y una Bebop
ip route
# Esperado:
#   192.168.20.0/24 dev <eth0 o wlan0>   ← LAN
#   192.168.42.0/24 dev wlxc01c30430fbc  ← Bebop
```

Si la ruta al Bebop NO aparece automáticamente:
```bash
sudo ip route add 192.168.42.0/24 dev wlxc01c30430fbc
```

Si la conexión LAN se cayó al conectar el Bebop (nmcli reconfiguró default gw):
```bash
# Restaurar gateway LAN (ajustar IP del router si es diferente)
sudo ip route add default via 192.168.20.1 dev <interfaz_lan>
```

## PASO 4: Instalar Olympe SDK

```bash
# Opción A: pip directo (suele funcionar en Mint/Ubuntu)
pip3 install parrot-olympe

# Si falla, Opción B: desde el repo oficial de Parrot
pip3 install olympe

# Si ambas fallan, Opción C: instalar desde fuente
sudo apt-get install -y python3-dev libavcodec-dev libavformat-dev libavutil-dev \
    libswscale-dev libfreetype6-dev libjpeg-dev zlib1g-dev
pip3 install git+https://github.com/Parrot-Developers/olympe.git

# Verificar instalación
python3 -c "import olympe; print('Olympe OK:', olympe.__version__)"
```

## PASO 5: Crear el drone bridge

Crea el fichero `~/drone_bridge.py` con este contenido **exacto**:

```python
#!/usr/bin/env python3
"""
Seedy Drone Bridge — Corre en el HOST (Dell Latitude).

Conecta con el Bebop 2 vía Olympe SDK y expone un mini HTTP API
que el backend Seedy (Docker en MSI) llama para ejecutar vuelos.

Uso:
  python3 drone_bridge.py
"""

import json
import time
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("drone-bridge")

BEBOP_IP = "192.168.42.1"
LISTEN_PORT = 9090

# Plan de vuelo anti-gorriones
FORWARD_M = 20.0    # metros hacia el comedero (norte)
ALTITUDE_M = 2.5    # metros de altura
HOVER_S = 5          # segundos hovering

drone = None
is_flying = False


def connect_drone():
    global drone
    try:
        import olympe
        drone = olympe.Drone(BEBOP_IP)
        drone.connect()
        logger.info(f"Dron conectado ({BEBOP_IP})")
        return True
    except Exception as e:
        logger.error(f"Error conectando al dron: {e}")
        return False


def execute_flight() -> dict:
    global is_flying
    if is_flying:
        return {"status": "error", "reason": "already_flying"}

    is_flying = True
    t0 = time.time()
    try:
        if drone is None:
            return {"status": "error", "reason": "not_connected"}

        from olympe.messages.ardrone3.Piloting import TakeOff, Landing, moveBy

        logger.info("Despegando...")
        drone(TakeOff()).wait()
        time.sleep(3)

        logger.info(f"Subiendo a {ALTITUDE_M}m...")
        drone(moveBy(0, 0, -ALTITUDE_M, 0)).wait()
        time.sleep(2)

        logger.info(f"Avanzando {FORWARD_M}m al comedero...")
        drone(moveBy(FORWARD_M, 0, 0, 0)).wait()
        time.sleep(1)

        logger.info(f"Hovering {HOVER_S}s...")
        time.sleep(HOVER_S)

        logger.info(f"Regresando {FORWARD_M}m...")
        drone(moveBy(-FORWARD_M, 0, 0, 0)).wait()
        time.sleep(2)

        logger.info("Aterrizando...")
        drone(Landing()).wait()

        duration = time.time() - t0
        return {"status": "completed", "duration_s": round(duration, 1)}

    except Exception as e:
        logger.error(f"Error en vuelo: {e}")
        try:
            from olympe.messages.ardrone3.Piloting import Landing
            drone(Landing()).wait()
        except Exception:
            pass
        return {"status": "error", "reason": str(e), "duration_s": round(time.time() - t0, 1)}
    finally:
        is_flying = False


class DroneHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            data = {
                "connected": drone is not None,
                "is_flying": is_flying,
                "bebop_ip": BEBOP_IP,
            }
            self._json_response(200, data)
        elif self.path == "/health":
            self._json_response(200, {"ok": True})
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/fly":
            result = execute_flight()
            self._json_response(200, result)
        elif self.path == "/connect":
            ok = connect_drone()
            self._json_response(200, {"connected": ok})
        else:
            self._json_response(404, {"error": "not found"})

    def _json_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")


if __name__ == "__main__":
    logger.info(f"Drone bridge starting on :{LISTEN_PORT}")
    logger.info(f"Bebop IP: {BEBOP_IP}")
    logger.info("Intentando conectar al dron...")
    connect_drone()
    server = HTTPServer(("0.0.0.0", LISTEN_PORT), DroneHandler)
    logger.info(f"Listening on http://0.0.0.0:{LISTEN_PORT}")
    logger.info("  GET  /status  — estado del dron")
    logger.info("  POST /fly     — ejecutar vuelo anti-gorriones")
    logger.info("  POST /connect — reconectar al dron")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if drone:
            drone.disconnect()
```

## PASO 6: Lanzar el bridge

```bash
python3 ~/drone_bridge.py
```

Deberías ver:
```
2026-03-27 ... [INFO] Drone bridge starting on :9090
2026-03-27 ... [INFO] Bebop IP: 192.168.42.1
2026-03-27 ... [INFO] Intentando conectar al dron...
2026-03-27 ... [INFO] Dron conectado (192.168.42.1)
2026-03-27 ... [INFO] Listening on http://0.0.0.0:9090
```

Si dice "Error conectando al dron", verifica `ping 192.168.42.1`.

## PASO 7: Verificar desde la MSI

Desde otra terminal (o pídele a otro copilot en la MSI):
```bash
curl http://192.168.20.102:9090/status
# Debe devolver: {"connected": true, "is_flying": false, "bebop_ip": "192.168.42.1"}
```

## PASO 8: Test de vuelo (CUIDADO — EL DRON DESPEGARÁ)

⚠️ **Solo ejecutar con espacio despejado y dron en superficie plana.**

```bash
curl -X POST http://192.168.20.102:9090/fly
# El Bebop despegará, volará 20m, hoverá 5s, volverá y aterrizará
```

---

## Troubleshooting

| Problema | Solución |
|----------|----------|
| `nmcli` no conecta al Bebop | `sudo nmcli device wifi rescan ifname wlxc01c30430fbc` y reintentar |
| No hay ruta a 192.168.42.0 | `sudo ip route add 192.168.42.0/24 dev wlxc01c30430fbc` |
| Se pierde conexión LAN al conectar Bebop | `sudo ip route add default via 192.168.20.1 dev <eth_interfaz>` |
| Olympe no importa | Verificar: `python3 -c "import olympe"` — puede necesitar compilar desde fuente |
| Puerto 9090 rechazado desde MSI | `sudo ufw allow 9090/tcp` o verificar firewall |
| Dron no despega | Verificar batería >30%, firmware actualizado, GPS no requerido para indoor |

---

## Arquitectura de red

```
[Bebop 2]  ←WiFi 192.168.42.1→  [Dongle AR9271 en Latitude]
                                   wlxc01c30430fbc
                                   192.168.42.x

[Latitude]  ←LAN 192.168.20.102→  [MSI Vector 192.168.20.131]
  drone_bridge.py :9090               seedy-backend (Docker)
                                       → DRONE_BRIDGE_URL=http://192.168.20.102:9090
```
