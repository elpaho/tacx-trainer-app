import asyncio
import struct
import logging
from collections import deque
from bleak import BleakClient, BleakScanner
from models.data import MetricsData, ConnectionState

logger = logging.getLogger(__name__)

# Tacx Neo 2T — FE-C over BLE UUIDs
# NAPOMENA: Na Neo 2T UUID-ovi su zamijenjeni u odnosu na dokumentaciju!
FEC_SERVICE   = "6e40fec1-b5a3-f393-e0a9-e50e24dcca9e"
FEC_NOTIFY    = "6e40fec2-b5a3-f393-e0a9-e50e24dcca9e"  # notify (prima podatke)
FEC_WRITE     = "6e40fec3-b5a3-f393-e0a9-e50e24dcca9e"  # write (šalje naredbe)

# Standardni BLE profili
CPS_SERVICE   = "00001818-0000-1000-8000-00805f9b34fb"
CPS_POWER     = "00002a63-0000-1000-8000-00805f9b34fb"  # [notify]
CPS_CRANK     = "00002a64-0000-1000-8000-00805f9b34fb"  # [notify]
CPS_CONTROL   = "00002a66-0000-1000-8000-00805f9b34fb"  # [write, indicate]
CSCS_SERVICE  = "00001816-0000-1000-8000-00805f9b34fb"
CSCS_MEASURE  = "00002a5b-0000-1000-8000-00805f9b34fb"  # [notify]


class TacxTrainer:
    """
    BLE komunikacija s Tacx Neo 2T trenažerom.
    Koristi CPS za snagu/kadencu i FEC za brzinu i kontrolu.
    Interni timer agregira podatke i šalje ih UI-u jednom u sekundi.
    """

    def __init__(self, on_metrics=None, on_state_change=None):
        self.on_metrics = on_metrics
        self.on_state_change = on_state_change

        self._client: BleakClient | None = None
        self.state = ConnectionState.DISCONNECTED

        # raw vrijednosti koje callbacki upisuju
        self._raw_power: int = 0
        self._raw_cadence: int = 0
        self._speed: float = 0.0
        self._target_power: int = 0

        # L/R balance i smoothness iz CPS
        self._balance_left: float = 0.0
        self._smoothness_left: float = 0.0
        self._smoothness_right: float = 0.0

        # 3s rolling buffer za snagu
        self._power_buf: deque = deque([0, 0, 0], maxlen=3)

        # za izračun kadence iz crank data
        self._crank_history: list = []  # lista (revs, timestamp)
        self._cadence_buf: deque = deque([0, 0, 0], maxlen=3)

        # interval averages
        self._int_power_sum: float = 0
        self._int_power_cnt: int = 0
        self._int_hr_sum: float = 0
        self._int_hr_cnt: int = 0

        # emit timer
        self._emit_task: asyncio.Task | None = None

    async def connect(self, address: str):
        self._set_state(ConnectionState.CONNECTING)
        try:
            self._client = BleakClient(address)
            await self._client.connect()
            logger.info(f"Spojen na {address}")

            # FEC page 25 daje snagu, kadencu i status
            # FEC page 16 daje brzinu
            await self._client.start_notify(FEC_NOTIFY, self._on_fec_notification)
            logger.info("FEC notify OK")

            # CPS — L/R balance i pedal smoothness (ako trenažer podržava)
            try:
                await self._client.start_notify(CPS_POWER, self._on_cps_power)
                logger.info("CPS notify OK")
            except Exception as e:
                logger.warning(f"CPS notify nije dostupan: {e}")

            self._set_state(ConnectionState.CONNECTED)
            self._emit_task = asyncio.ensure_future(self._emit_loop())

        except Exception as e:
            logger.error(f"Greška pri spajanju: {e}")
            self._set_state(ConnectionState.DISCONNECTED)
            raise

    async def disconnect(self):
        if self._emit_task:
            self._emit_task.cancel()
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._set_state(ConnectionState.DISCONNECTED)

    async def _emit_loop(self):
        """Šalje agregirane metrike UI-u jednom u sekundi."""
        while self._client and self._client.is_connected:
            await asyncio.sleep(1.0)

            self._power_buf.append(self._raw_power)
            power_3s = round(sum(self._power_buf) / len(self._power_buf))

            if self._raw_power > 0:
                self._int_power_sum += self._raw_power
                self._int_power_cnt += 1
            int_avg_pw = round(self._int_power_sum / self._int_power_cnt) if self._int_power_cnt else 0

            metrics = MetricsData(
                power=self._raw_power,
                power_3s=power_3s,
                cadence=self._raw_cadence,
                speed=self._speed,
                interval_avg_power=int_avg_pw,
                target_power=self._target_power,
                balance_left=self._balance_left,
                smoothness_left=self._smoothness_left,
                smoothness_right=self._smoothness_right,
            )
            if self.on_metrics:
                self.on_metrics(metrics)

    def reset_interval_stats(self):
        self._int_power_sum = 0
        self._int_power_cnt = 0
        self._int_hr_sum = 0
        self._int_hr_cnt = 0

    async def set_target_power(self, watts: int):
        """ERG mod — FEC page 49, format prema pycycling/ANT+ FE-C spec."""
        if not self._is_connected():
            return
        self._target_power = watts
        watts = max(0, min(4000, watts))
        # power u 0.25W jedinicama
        target = round(watts * 4)
        payload = bytearray([
            0xA4, 0x09, 0x4F, 0x05,
            0x31,  # page 49
            0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
            target & 0xFF,
            (target >> 8) & 0xFF,
        ])
        payload.append(self._checksum(payload))
        try:
            await self._client.write_gatt_char(FEC_WRITE, payload, response=False)
        except Exception as e:
            logger.error(f"Greška set_target_power: {e}")

    async def set_grade(self, grade_pct: float):
        """Slope mod — FEC page 51 Track Resistance."""
        if not self._is_connected():
            return
        grade_raw = round((grade_pct + 200) * 100)
        grade_raw = max(0, min(65535, grade_raw))
        payload = bytearray([
            0xA4, 0x09, 0x4F, 0x05,
            0x33,
            0xFF, 0xFF, 0xFF, 0xFF,
            grade_raw & 0xFF,
            (grade_raw >> 8) & 0xFF,
            0xFF,
        ])
        payload.append(self._checksum(payload))
        try:
            await self._client.write_gatt_char(FEC_WRITE, payload, response=False)
        except Exception as e:
            logger.error(f"Greška set_grade: {e}")

    # ------------------------------------------------------------------ callbacks

    # ------------------------------------------------------------------ callbacks

    def _on_cps_power(self, sender, data: bytearray):
        """
        CPS 0x2a63 — Cycling Power Measurement.
        Parsira L/R balance i pedal smoothness ako su dostupni u paketu.

        CPS flags (bytes 0-1):
          bit 0: Pedal Power Balance Present
          bit 1: Pedal Power Balance Reference (0=unknown, 1=left)
          bit 2: Accumulated Torque Present
          bit 3: Accumulated Torque Source
          bit 4: Wheel Revolution Data Present
          bit 5: Crank Revolution Data Present
          bit 6: Extreme Force Magnitudes Present
          bit 7: Extreme Torque Magnitudes Present
          bit 8: Extreme Angles Present
          bit 9: Top Dead Spot Angle Present
          bit 10: Bottom Dead Spot Angle Present
          bit 11: Accumulated Energy Present
          bit 12: Offset Compensation Indicator
          bit 13: Left/Right Pedal Smoothness Present (oba zajedno)
        """
        if len(data) < 4:
            return

        flags = int.from_bytes(data[0:2], "little")
        offset = 4  # preskačemo flags (2) i instantaneous power (2)

        # Pedal Power Balance (bit 0)
        if flags & 0x0001:
            if offset < len(data):
                raw_balance = data[offset]
                # vrijednost je u 0.5% koracima, referenca je lijeva noga
                self._balance_left = raw_balance * 0.5
                offset += 1

        # Accumulated Torque (bit 2) — preskačemo, 2 bajta
        if flags & 0x0004:
            offset += 2

        # Wheel Revolution Data (bit 4) — preskačemo, 6 bajta
        if flags & 0x0010:
            offset += 6

        # Crank Revolution Data (bit 5) — preskačemo, 4 bajta
        if flags & 0x0020:
            offset += 4

        # Extreme Force Magnitudes (bit 6) — preskačemo, 4 bajta
        if flags & 0x0040:
            offset += 4

        # Extreme Torque Magnitudes (bit 7) — preskačemo, 4 bajta
        if flags & 0x0080:
            offset += 4

        # Extreme Angles (bit 8) — preskačemo, 3 bajta
        if flags & 0x0100:
            offset += 3

        # Top Dead Spot Angle (bit 9) — preskačemo, 2 bajta
        if flags & 0x0200:
            offset += 2

        # Bottom Dead Spot Angle (bit 10) — preskačemo, 2 bajta
        if flags & 0x0400:
            offset += 2

        # Accumulated Energy (bit 11) — preskačemo, 2 bajta
        if flags & 0x0800:
            offset += 2

        # Left/Right Pedal Smoothness (bit 13) — svaki po 1 bajt, u 0.5% koracima
        if flags & 0x2000:
            if offset + 1 < len(data):
                raw_l = data[offset]
                raw_r = data[offset + 1]
                # 0xFF = vrijednost nije dostupna
                if raw_l != 0xFF:
                    self._smoothness_left = raw_l * 0.5
                if raw_r != 0xFF:
                    self._smoothness_right = raw_r * 0.5

    def _on_cps_crank(self, sender, data: bytearray):
        """Nije više u upotrebi — sve dolazi iz FEC."""
        pass

    def _on_fec_notification(self, sender, data: bytearray):
        """
        Jedini izvor podataka — FEC notifikacije.
        Page 16: General FE Data — brzina (mm/s)
        Page 25: Trainer-Specific — snaga (W) i kadenca (rpm) direktno
        """
        if len(data) < 13:
            return
        page = data[4]

        if page == 16:
            # byte 9-10: brzina u mm/s
            speed_raw = data[9] | (data[10] << 8)
            self._speed = round(speed_raw * 0.001 * 3.6, 1)  # mm/s → km/h

        elif page == 25:
            # byte 6: kadenca (rpm), 0xFF = invalid/nema podatka
            cadence = data[6]
            if cadence != 0xFF:
                self._raw_cadence = cadence

            # byte 9 + donji nibble byte 10: instantaneous power (W)
            power = (data[10] & 0x0F) << 8 | data[9]
            if power > 0:
                self._raw_power = power

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _checksum(data: bytearray) -> int:
        chk = 0
        for b in data:
            chk ^= b
        return chk

    def _is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _set_state(self, state: ConnectionState):
        self.state = state
        if self.on_state_change:
            self.on_state_change(state)
