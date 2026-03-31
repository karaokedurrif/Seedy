#!/usr/bin/env python3
"""
Seedy Drone Bridge — Corre en el HOST (no en Docker).

Conecta con el Bebop 2 vía Olympe SDK y expone un mini HTTP API
que el backend Docker llama para ejecutar vuelos.

Requisitos (en el host):
  pip install parrot-olympe
  # o: pip install olympe  (según versión)

Uso:
  python3 drone_bridge.py

El backend llama a http://host.docker.internal:9090/fly
para ejecutar un vuelo anti-gorriones.
"""

import json
import time
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("drone-bridge")

BEBOP_IP = "192.168.42.1"
LISTEN_PORT = 9090

# Plan de vuelo
FORWARD_M = 20.0
ALTITUDE_M = 2.5
HOVER_S = 5

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
        # Emergencia: aterrizar
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
