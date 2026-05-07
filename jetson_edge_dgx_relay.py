"""
Seedy Edge v4.5 — DGX Backend Relay
Jetson Orin Nano 8GB

Publicar eventos de tracking al backend DGX con retry + Redis failover.
"""

import time
import json
import logging
from typing import Dict, Any, Optional
import httpx
import redis

logger = logging.getLogger(__name__)


class DGXRelay:
    """
    Cliente para enviar eventos edge al backend DGX.
    Retry automático + cola Redis failover.
    """
    
    def __init__(
        self,
        dgx_url: str,
        endpoint: str,
        timeout: float = 5.0,
        retry_attempts: int = 3,
        retry_delay: float = 2.0,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_queue_key: str = "seedy:edge:events",
        max_queue_size: int = 1000
    ):
        self.dgx_url = dgx_url
        self.endpoint = endpoint
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        
        # Redis failover queue
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        self.redis_queue_key = redis_queue_key
        self.max_queue_size = max_queue_size
        
        # HTTP client async
        self.http_client = httpx.AsyncClient(timeout=timeout)
        
        # Stats
        self.events_sent = 0
        self.events_failed = 0
        self.events_queued = 0
        self.total_latency = 0.0
    
    async def publish_event(self, event: Dict[str, Any]) -> bool:
        """
        Publicar evento al backend DGX.
        
        Args:
            event: Dict con schema v4.5
            
        Returns:
            True si enviado con éxito, False si falló y se encoló
        """
        url = f"{self.dgx_url}{self.endpoint}"
        
        for attempt in range(1, self.retry_attempts + 1):
            try:
                start = time.time()
                
                response = await self.http_client.post(
                    url,
                    json=event,
                    headers={"Content-Type": "application/json"}
                )
                
                latency = time.time() - start
                self.total_latency += latency
                
                if response.status_code == 200:
                    self.events_sent += 1
                    
                    if self.events_sent % 100 == 0:
                        avg_latency = self.total_latency / self.events_sent
                        logger.info(
                            f"📡 Eventos enviados: {self.events_sent} — "
                            f"avg latency: {avg_latency*1000:.0f}ms"
                        )
                    
                    return True
                else:
                    logger.warning(
                        f"Backend devolvió {response.status_code} (intento {attempt}/{self.retry_attempts})"
                    )
                    
            except Exception as e:
                logger.warning(
                    f"Error enviando evento (intento {attempt}/{self.retry_attempts}): {e}"
                )
            
            # Esperar antes del siguiente intento
            if attempt < self.retry_attempts:
                await asyncio.sleep(self.retry_delay)
        
        # Todos los intentos fallaron → encolar en Redis
        logger.error(f"❌ Evento falló tras {self.retry_attempts} intentos, encolando en Redis")
        self._enqueue_to_redis(event)
        self.events_failed += 1
        return False
    
    def _enqueue_to_redis(self, event: Dict[str, Any]):
        """Encolar evento en Redis para retry posterior."""
        try:
            queue_size = self.redis_client.llen(self.redis_queue_key)
            
            if queue_size >= self.max_queue_size:
                logger.error(
                    f"⚠️ Redis queue llena ({queue_size}/{self.max_queue_size}), "
                    f"descartando evento más antiguo"
                )
                self.redis_client.lpop(self.redis_queue_key)
            
            self.redis_client.rpush(
                self.redis_queue_key,
                json.dumps(event)
            )
            self.events_queued += 1
            
            logger.info(f"📥 Evento encolado en Redis (queue size: {queue_size + 1})")
            
        except Exception as e:
            logger.error(f"❌ Error encolando en Redis: {e}")
    
    async def flush_queue(self) -> int:
        """
        Intentar reenviar eventos encolados en Redis.
        
        Returns:
            Número de eventos reenviados con éxito
        """
        try:
            queue_size = self.redis_client.llen(self.redis_queue_key)
            if queue_size == 0:
                return 0
            
            logger.info(f"🔄 Flushing Redis queue ({queue_size} eventos pendientes)...")
            
            flushed = 0
            errors = 0
            
            for _ in range(queue_size):
                event_json = self.redis_client.lpop(self.redis_queue_key)
                if event_json is None:
                    break
                
                event = json.loads(event_json)
                success = await self.publish_event(event)
                
                if success:
                    flushed += 1
                else:
                    errors += 1
                    # Si falla, publish_event ya lo vuelve a encolar
                    break  # Dejar de flush si el backend sigue caído
            
            logger.info(
                f"✅ Flush completado: {flushed} reenviados, {errors} errores"
            )
            return flushed
            
        except Exception as e:
            logger.error(f"❌ Error en flush_queue: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas del relay."""
        queue_size = 0
        try:
            queue_size = self.redis_client.llen(self.redis_queue_key)
        except:
            pass
        
        avg_latency = (
            self.total_latency / self.events_sent
            if self.events_sent > 0 else 0
        )
        
        return {
            "events_sent": self.events_sent,
            "events_failed": self.events_failed,
            "events_queued": self.events_queued,
            "queue_size": queue_size,
            "avg_latency_ms": avg_latency * 1000,
            "success_rate": (
                self.events_sent / (self.events_sent + self.events_failed)
                if (self.events_sent + self.events_failed) > 0 else 1.0
            )
        }
    
    async def close(self):
        """Cerrar cliente HTTP."""
        await self.http_client.aclose()


# Necesario para async
import asyncio


if __name__ == "__main__":
    # Test básico
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    async def test():
        relay = DGXRelay(
            dgx_url="http://192.168.20.131:8000",
            endpoint="/vision/edge_event",
            timeout=5.0,
            retry_attempts=2
        )
        
        # Evento de prueba
        test_event = {
            "schema_version": "4.5",
            "timestamp": time.time(),
            "edge_node_id": "jetson_test",
            "camera_id": "test_camera",
            "gallinero_id": "gallinero_palacio",
            "event_type": "tracking",
            "tracks": []
        }
        
        success = await relay.publish_event(test_event)
        print(f"{'✅' if success else '❌'} Evento enviado")
        
        stats = relay.get_stats()
        print(f"📊 Stats: {stats}")
        
        await relay.close()
    
    asyncio.run(test())
