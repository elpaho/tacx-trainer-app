import asyncio
import builtins
import logging
from collections import deque
from PyQt6.QtCore import QObject, pyqtSignal
from bleak import BleakClient

logger = logging.getLogger(__name__)

HRS_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HRS_MEASURE = "00002a37-0000-1000-8000-00805f9b34fb"

__all__ = ["HRS_SERVICE", "HRS_MEASURE", "HeartRateMonitor"]


def _run_async(coro):
    loop = getattr(builtins, '_asyncio_loop', None)
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, loop)


class HeartRateMonitor(QObject):
    """BLE pulsmetar — standardni Heart Rate Service (HRS)."""

    hr_updated = pyqtSignal(int)

    def __init__(self, on_hr=None):
        super().__init__()
        self._client: BleakClient | None = None
        self.connected: bool = False
        self.current_hr: int = 0
        self._buf: deque = deque(maxlen=3)  # 3s smoothing
        if on_hr:
            self.hr_updated.connect(on_hr)

    async def _connect_async(self, address: str):
        try:
            self._client = BleakClient(address)
            await self._client.connect()
            await self._client.start_notify(HRS_MEASURE, self._on_notification)
            self.connected = True
            logger.info(f"Pulsmetar spojen: {address}")
        except Exception as e:
            logger.error(f"HR connect greška: {e}")
            self.connected = False
            raise

    async def disconnect(self):
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self.connected = False

    def _on_notification(self, sender, data: bytearray):
        """BLE callback iz asyncio threada — emit je thread-safe kroz Qt signal."""
        flags = data[0]
        hr = int.from_bytes(data[1:3], "little") if flags & 0x01 else data[1]
        if hr > 0:
            self._buf.append(hr)
            smoothed = round(sum(self._buf) / len(self._buf))
            self.current_hr = smoothed
            self.hr_updated.emit(smoothed)
