"""Seedy Backend — CPU Watchdog.

Monitorea el uso de CPU y ajusta dinámicamente la cadencia
del CaptureManager para evitar saturación. La GPU (RTX 5080)
tiene VRAM de sobra; el cuello de botella es CPU por el
pre/post-processing de YOLO (JPEG decode, numpy, NMS).

Estrategia:
  - CPU > 80% durante 10s → aumentar frame_skip (throttle)
  - CPU > 90% → pausar sub-streams temporalmente
  - CPU < 60% durante 30s → reducir frame_skip (recover)
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore
    logger.warning("psutil not installed — CPU watchdog disabled")


# ─── Configuración ───

CPU_HIGH_THRESHOLD = float(os.environ.get("WATCHDOG_CPU_HIGH", "80"))
CPU_CRITICAL_THRESHOLD = float(os.environ.get("WATCHDOG_CPU_CRITICAL", "90"))
CPU_LOW_THRESHOLD = float(os.environ.get("WATCHDOG_CPU_LOW", "60"))
HIGH_DURATION = 10       # Segundos sobre HIGH para throttle
CRITICAL_DURATION = 5    # Segundos sobre CRITICAL para pause
LOW_DURATION = 30        # Segundos bajo LOW para recover
CHECK_INTERVAL = 3       # Frecuencia de muestreo (segundos)
MIN_FRAME_SKIP = 2       # Mínimo frame_skip (valor default)
MAX_FRAME_SKIP = 8       # Máximo antes de pausar
PAUSE_COOLDOWN = 60      # Segundos de pausa antes de reintentar


@dataclass
class WatchdogState:
    """Estado actual del watchdog."""
    cpu_percent: float = 0.0
    frame_skip: int = MIN_FRAME_SKIP
    paused: bool = False
    throttle_level: int = 0        # 0=normal, 1=throttled, 2=paused
    high_since: float = 0.0        # Timestamp desde que CPU > HIGH
    critical_since: float = 0.0    # Timestamp desde que CPU > CRITICAL
    low_since: float = 0.0         # Timestamp desde que CPU < LOW
    last_pause: float = 0.0
    throttle_events: int = 0
    pause_events: int = 0
    recover_events: int = 0


class CPUWatchdog:
    """Vigila CPU y ajusta CaptureManager dinámicamente."""

    def __init__(self):
        self.state = WatchdogState()
        self._task: asyncio.Task | None = None
        self._running = False
        self._callbacks_throttle: list = []
        self._callbacks_pause: list = []
        self._callbacks_resume: list = []

    def on_throttle(self, cb):
        """Registrar callback cuando se hace throttle: cb(new_frame_skip)."""
        self._callbacks_throttle.append(cb)

    def on_pause(self, cb):
        """Registrar callback cuando se pausa: cb()."""
        self._callbacks_pause.append(cb)

    def on_resume(self, cb):
        """Registrar callback cuando se recupera: cb(new_frame_skip)."""
        self._callbacks_resume.append(cb)

    @property
    def frame_skip(self) -> int:
        return self.state.frame_skip

    @property
    def is_paused(self) -> bool:
        return self.state.paused

    def get_status(self) -> dict:
        return {
            "cpu_percent": self.state.cpu_percent,
            "frame_skip": self.state.frame_skip,
            "paused": self.state.paused,
            "throttle_level": self.state.throttle_level,
            "throttle_events": self.state.throttle_events,
            "pause_events": self.state.pause_events,
            "recover_events": self.state.recover_events,
        }

    async def start(self):
        if psutil is None:
            logger.warning("CPU watchdog disabled (psutil not available)")
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop(), name="cpu_watchdog")
        logger.info(
            f"🛡️ CPU Watchdog started: high={CPU_HIGH_THRESHOLD}%, "
            f"critical={CPU_CRITICAL_THRESHOLD}%, low={CPU_LOW_THRESHOLD}%"
        )

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _monitor_loop(self):
        while self._running:
            try:
                # Muestrear CPU (interval=1 para no bloquear)
                cpu = await asyncio.to_thread(psutil.cpu_percent, interval=1)
                self.state.cpu_percent = cpu
                now = time.time()

                if cpu >= CPU_CRITICAL_THRESHOLD:
                    # CPU crítica
                    if self.state.critical_since == 0:
                        self.state.critical_since = now
                    elif now - self.state.critical_since >= CRITICAL_DURATION:
                        await self._do_pause(now)
                    self.state.low_since = 0

                elif cpu >= CPU_HIGH_THRESHOLD:
                    # CPU alta — throttle
                    self.state.critical_since = 0
                    if self.state.high_since == 0:
                        self.state.high_since = now
                    elif now - self.state.high_since >= HIGH_DURATION:
                        await self._do_throttle()
                    self.state.low_since = 0

                elif cpu < CPU_LOW_THRESHOLD:
                    # CPU baja — recover
                    self.state.high_since = 0
                    self.state.critical_since = 0
                    if self.state.low_since == 0:
                        self.state.low_since = now
                    elif now - self.state.low_since >= LOW_DURATION:
                        await self._do_recover()

                else:
                    # CPU entre LOW y HIGH — estable, resetear timers
                    self.state.high_since = 0
                    self.state.critical_since = 0
                    self.state.low_since = 0

                await asyncio.sleep(CHECK_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Watchdog error: {e}")
                await asyncio.sleep(CHECK_INTERVAL)

    async def _do_throttle(self):
        old_skip = self.state.frame_skip
        new_skip = min(old_skip + 2, MAX_FRAME_SKIP)
        if new_skip == old_skip and not self.state.paused:
            # Ya al máximo throttle pero sin pausar aún
            return
        self.state.frame_skip = new_skip
        self.state.throttle_level = 1
        self.state.throttle_events += 1
        self.state.high_since = 0  # Reset para no re-triggear inmediato
        logger.warning(
            f"🛡️ CPU Watchdog THROTTLE: CPU={self.state.cpu_percent:.0f}%, "
            f"frame_skip {old_skip}→{new_skip}"
        )
        for cb in self._callbacks_throttle:
            try:
                cb(new_skip)
            except Exception:
                pass

    async def _do_pause(self, now: float):
        if self.state.paused:
            return
        if now - self.state.last_pause < PAUSE_COOLDOWN:
            return  # Evitar flip-flop
        self.state.paused = True
        self.state.throttle_level = 2
        self.state.pause_events += 1
        self.state.last_pause = now
        self.state.critical_since = 0
        logger.warning(
            f"🛡️ CPU Watchdog PAUSE: CPU={self.state.cpu_percent:.0f}%, "
            f"sub-streams pausados por {PAUSE_COOLDOWN}s"
        )
        for cb in self._callbacks_pause:
            try:
                cb()
            except Exception:
                pass
        # Auto-resume después del cooldown
        asyncio.get_event_loop().call_later(
            PAUSE_COOLDOWN, lambda: asyncio.ensure_future(self._auto_resume())
        )

    async def _auto_resume(self):
        if not self.state.paused:
            return
        cpu = await asyncio.to_thread(psutil.cpu_percent, interval=1)
        if cpu < CPU_HIGH_THRESHOLD:
            await self._do_recover()
        else:
            # Sigue alta, extender pausa
            logger.warning(
                f"🛡️ CPU Watchdog: CPU still {cpu:.0f}% after pause, extending"
            )
            self.state.last_pause = time.time()
            asyncio.get_event_loop().call_later(
                PAUSE_COOLDOWN, lambda: asyncio.ensure_future(self._auto_resume())
            )

    async def _do_recover(self):
        old_skip = self.state.frame_skip
        was_paused = self.state.paused
        self.state.frame_skip = MIN_FRAME_SKIP
        self.state.paused = False
        self.state.throttle_level = 0
        self.state.low_since = 0
        if was_paused or old_skip > MIN_FRAME_SKIP:
            self.state.recover_events += 1
            logger.info(
                f"🛡️ CPU Watchdog RECOVER: CPU={self.state.cpu_percent:.0f}%, "
                f"frame_skip→{MIN_FRAME_SKIP}, paused→False"
            )
            for cb in self._callbacks_resume:
                try:
                    cb(MIN_FRAME_SKIP)
                except Exception:
                    pass


# ─── Singleton ───

_watchdog: CPUWatchdog | None = None


def get_cpu_watchdog() -> CPUWatchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = CPUWatchdog()
    return _watchdog
