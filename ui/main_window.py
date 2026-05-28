import asyncio
import builtins
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QGridLayout, QLabel, QPushButton, QSlider, QFileDialog,
    QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMetaObject, Q_ARG
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis

from models.data import MetricsData, Workout, TrainerMode, ConnectionState
from workout.player import WorkoutPlayer

logger = logging.getLogger(__name__)


def run_async(coro):
    """Pokreni coroutine u asyncio loopu koji radi u zasebnom threadu."""
    loop = getattr(builtins, '_asyncio_loop', None)
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        asyncio.ensure_future(coro)


class MetricCard(QFrame):
    """Jedna metrika (label + vrijednost + jedinica)."""

    def __init__(self, label: str, unit: str, secondary: bool = False):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        if secondary:
            self.setObjectName("metricCardSecondary")
        else:
            self.setObjectName("metricCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self.lbl = QLabel(label.upper())
        self.lbl.setObjectName("metricLabel")
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value = QLabel("—")
        self.value.setObjectName("metricValueSecondary" if secondary else "metricValue")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.unit_lbl = QLabel(unit)
        self.unit_lbl.setObjectName("metricUnit")
        self.unit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.lbl)
        layout.addWidget(self.value)
        layout.addWidget(self.unit_lbl)

    def set_value(self, v: str):
        self.value.setText(str(v))

    def set_unit(self, u: str):
        self.unit_lbl.setText(u)



class IntervalDotsWidget(QWidget):
    """
    Prikaz napretka intervala kao lampice.
    Ugašena=tamno siva, Trenutni=zlatni rub, Zelena/Crvena=odrađeni.
    """
    COLOR_DONE_OK     = QColor("#009e80")   # ±5% — zelena
    COLOR_DONE_GREAT  = QColor("#639922")   # >5% jači — jača zelena
    COLOR_DONE_FAIL   = QColor("#dd0447")   # ispod -5% — crvena
    COLOR_CURRENT     = QColor("#0e1015")   # unutrašnjost trenutnog
    COLOR_FUTURE      = QColor("#1e2230")   # budući

    def __init__(self):
        super().__init__()
        self._intervals: list = []
        self._current_idx: int = -1
        self._results: list[int] = []
        self.setFixedHeight(28)
        self.setSizePolicy(
            __import__("PyQt6.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Policy.Expanding,
            __import__("PyQt6.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Policy.Fixed
        )

    def set_intervals(self, intervals: list):
        self._intervals = intervals
        self._current_idx = -1
        self._results = [0] * len(intervals)
        self.update()

    def set_current(self, idx: int):
        if idx != self._current_idx:
            self._current_idx = idx
            self.update()

    def set_result(self, idx: int, result: int):
        """result: 1=ok, 2=odlično, 3=fail"""
        if 0 <= idx < len(self._results):
            self._results[idx] = result
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if not self._intervals:
            return
        n = len(self._intervals)
        DOT = 16
        GAP = 5
        total_w = n * DOT + (n - 1) * GAP
        x0 = max(4, (W - total_w) // 2)
        cy = H // 2

        for i in range(n):
            x = x0 + i * (DOT + GAP)
            r = DOT // 2

            if i == self._current_idx:
                painter.setBrush(QColor("#1a1d24"))
                painter.setPen(QPen(QColor("#c8a84b"), 2))
            elif self._results[i] == 1:
                painter.setBrush(self.COLOR_DONE_OK)
                painter.setPen(QPen(QColor("#007060"), 1))
            elif self._results[i] == 2:
                painter.setBrush(self.COLOR_DONE_GREAT)
                painter.setPen(QPen(QColor("#3a6010"), 1))
            elif self._results[i] == 3:
                painter.setBrush(self.COLOR_DONE_FAIL)
                painter.setPen(QPen(QColor("#aa0030"), 1))
            else:
                # Ugašena — vidljiva tamno siva s rubom
                painter.setBrush(QColor("#252830"))
                painter.setPen(QPen(QColor("#404858"), 1))

            painter.drawEllipse(x, cy - r, DOT, DOT)

class TimeAxisWidget(QWidget):
    """Vremenska os ispod interval bara — crtica svake 5 min, label svake 10 min."""

    def __init__(self):
        super().__init__()
        self._total_duration: int = 0
        self.setFixedHeight(16)

    def set_total_duration(self, seconds: int):
        self._total_duration = seconds
        self.update()

    def paintEvent(self, event):
        if self._total_duration <= 0:
            return
        from PyQt6.QtGui import QFont
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        total = self._total_duration

        font = QFont()
        font.setPixelSize(9)
        painter.setFont(font)

        step_5  = 5 * 60   # 5 min u sekundama
        step_10 = 10 * 60

        t = step_5
        while t < total:
            x = int(t / total * W)
            is_10 = (t % step_10 == 0)
            # crtica
            painter.setPen(QPen(QColor("#3a4050"), 1))
            painter.drawLine(x, 0, x, 5 if is_10 else 3)
            # label samo na punima 10 min
            if is_10:
                minutes = t // 60
                lbl = str(minutes)
                fm = painter.fontMetrics()
                lbl_w = fm.horizontalAdvance(lbl)
                painter.setPen(QColor("#505868"))
                painter.drawText(x - lbl_w // 2, 15, lbl)
            t += step_5


class IntervalBar(QWidget):
    """Grafički prikaz intervala workota."""

    clicked = pyqtSignal(int)

    def __init__(self, intervals: list, current_idx: int = 0):
        super().__init__()
        self.intervals = intervals
        self.current_idx = current_idx
        self._progress = 0.0
        self.setMinimumHeight(40)
        self.setMouseTracking(True)

    def set_intervals(self, intervals, current_idx: int = 0):
        self.intervals = intervals
        self.current_idx = current_idx
        self.update()

    def set_current(self, idx: int):
        self.current_idx = idx
        self.update()

    def paintEvent(self, event):
        if not self.intervals:
            return
        from PyQt6.QtGui import QPolygonF, QLinearGradient, QBrush
        from PyQt6.QtCore import QPointF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        n = len(self.intervals)
        total_dur = sum(iv.duration for iv in self.intervals)
        if total_dur == 0:
            return

        # dinamički max za Y os — s paddingom za valoviti vrh slope intervala
        raw_max = max(
            max(max(iv.power_pct, getattr(iv, 'power_pct_end', iv.power_pct)) for iv in self.intervals),
            1.0
        )
        has_slope = any(getattr(iv, 'slope', None) is not None for iv in self.intervals)
        y_max = raw_max * (1.06 if has_slope else 1.02)  # 6% padding za val, 2% inače

        def scale_y(pct):
            return (pct / y_max) * h

        # proporcionalne X pozicije i širine prema trajanju
        GAP = 1  # manji gap za proporcionalni prikaz
        usable_w = w - (n - 1) * GAP
        x_positions = []
        bar_widths  = []
        cur_x = 0.0
        for iv in self.intervals:
            bw = usable_w * iv.duration / total_dur
            x_positions.append(cur_x)
            bar_widths.append(bw)
            cur_x += bw + GAP

        for i, iv in enumerate(self.intervals):
            x    = x_positions[i]
            bar_w = bar_widths[i]
            is_ramp = hasattr(iv, 'power_pct_end') and iv.type in ("ramp", "warmup", "cooldown")
            pct_end = getattr(iv, 'power_pct_end', iv.power_pct)

            color = self._interval_color(max(iv.power_pct, pct_end))
            if i != self.current_idx:
                color.setAlphaF(0.6)

            painter.setPen(Qt.PenStyle.NoPen)

            if is_ramp and abs(pct_end - iv.power_pct) > 0.01:
                h_start = scale_y(iv.power_pct)
                h_end = scale_y(pct_end)

                # multi-stop gradijent kroz sve zone između start i end
                grad = QLinearGradient(x, 0, x + bar_w, 0)
                pct_min = min(iv.power_pct, pct_end)
                pct_max = max(iv.power_pct, pct_end)
                zone_stops = [0.0, 0.55, 0.75, 0.90, 1.05, 1.20, 2.5]
                going_up = pct_end > iv.power_pct

                stops = []
                for z in zone_stops:
                    if pct_min <= z <= pct_max:
                        t = (z - pct_min) / (pct_max - pct_min)
                        if not going_up:
                            t = 1.0 - t
                        c = self._interval_color(z + 0.01)
                        c2 = QColor(c)
                        if i != self.current_idx:
                            c2.setAlphaF(0.6)
                        stops.append((t, c2))
                # uvijek dodaj start i end
                c_start = self._interval_color(iv.power_pct)
                c_end = self._interval_color(pct_end)
                if i != self.current_idx:
                    c_start.setAlphaF(0.6); c_end.setAlphaF(0.6)
                stops.insert(0, (0.0, c_start))
                stops.append((1.0, c_end))
                stops.sort(key=lambda s: s[0])
                for t, c in stops:
                    grad.setColorAt(t, c)

                painter.setBrush(QBrush(grad))
                poly = QPolygonF([
                    QPointF(x,          float(h)),
                    QPointF(x,          h - h_start),
                    QPointF(x + bar_w,  h - h_end),
                    QPointF(x + bar_w,  float(h)),
                ])
                painter.drawPolygon(poly)
            else:
                bar_h = scale_y(iv.power_pct)
                is_slope = getattr(iv, 'slope', None) is not None
                if is_slope:
                    from PyQt6.QtGui import QPolygonF, QPainterPath
                    from PyQt6.QtCore import QPointF
                    # Slope interval — fill s valovitim vrhom
                    bx0  = float(x)
                    by0  = float(h - bar_h)
                    bx1  = float(x + bar_w)
                    by1  = float(h)
                    # tijelo ispod vala — puna boja
                    wave_amp  = max(2.0, bar_h * 0.03)   # niža amplituda
                    wave_freq = max(2, int(bar_w / 24))   # širi val (duplo)
                    import math
                    # Izgradimo path: lijevo dolje → desno dolje → valoviti vrh
                    path = QPainterPath()
                    path.moveTo(bx0, by1)
                    path.lineTo(bx1, by1)
                    # valoviti vrh zdesna nalijevo
                    steps = max(32, int(bar_w))
                    for s in range(steps + 1):
                        t  = s / steps
                        px = bx1 - t * bar_w
                        py = by0 + wave_amp * math.sin(t * wave_freq * 2 * math.pi)
                        if s == 0:
                            path.lineTo(px, py)
                        else:
                            path.lineTo(px, py)
                    path.closeSubpath()
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(color)
                    painter.drawPath(path)
                else:
                    painter.setBrush(color)
                    painter.fillRect(int(x), int(h - bar_h), int(bar_w), int(bar_h), color)

            if i == self.current_idx:
                pass  # okomita crta je dovoljna, nema kvadrata

        # okomita crta napretka — jednom, izvan petlje
        if self.current_idx < n and self._progress > 0:
            x     = x_positions[self.current_idx]
            bar_w = bar_widths[self.current_idx]
            line_x = x + bar_w * self._progress
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(int(line_x), 0, int(line_x), h)

    def set_progress(self, progress: float):
        """progress = 0.0-1.0, napredak unutar trenutnog intervala."""
        self._progress = progress
        self.update()

    @property
    def progress_x_fraction(self) -> float:
        """X pozicija okomite crte kao udio ukupne širine (0.0-1.0)."""
        n = len(self.intervals)
        if n == 0 or self.current_idx >= n:
            return 0.0
        w = self.width()
        if w == 0:
            return 0.0
        total_dur = sum(iv.duration for iv in self.intervals)
        if total_dur == 0:
            return 0.0
        GAP = 1
        usable_w = w - (n - 1) * GAP
        cur_x = 0.0
        for i, iv in enumerate(self.intervals):
            bw = usable_w * iv.duration / total_dur
            if i == self.current_idx:
                line_x = cur_x + bw * self._progress
                return line_x / w
            cur_x += bw + GAP
        return 0.0

    def _interval_color(self, pct: float) -> QColor:
        """Boja prema FTP zoni — usklađeno s intervals.icu bojama."""
        if pct <= 0.0:  return QColor("#444444")   # freeride / pauza
        if pct <= 0.55: return QColor("#009e80")   # Z1 Active Recovery
        if pct <= 0.75: return QColor("#009e00")   # Z2 Endurance
        if pct <= 0.90: return QColor("#ffcb0e")   # Z3 Tempo
        if pct <= 1.05: return QColor("#ff7f0e")   # Z4 Threshold
        if pct <= 1.20: return QColor("#dd0447")   # Z5 VO2 Max
        if pct <= 1.50: return QColor("#6633cc")   # Z6 Anaerobic
        return QColor("#504861")                   # Z7 Neuromuscular

    def _idx_at_x(self, x: float) -> int:
        """Vrati indeks intervala na X poziciji."""
        if not self.intervals:
            return -1
        w = self.width()
        n = len(self.intervals)
        total_dur = sum(iv.duration for iv in self.intervals)
        if total_dur == 0:
            return -1
        GAP = 1
        usable_w = w - (n - 1) * GAP
        cur_x = 0.0
        for i, iv in enumerate(self.intervals):
            bw = usable_w * iv.duration / total_dur
            if cur_x <= x <= cur_x + bw:
                return i
            cur_x += bw + GAP
        return n - 1

    def mouseMoveEvent(self, event):
        if not self.intervals:
            return
        idx = self._idx_at_x(event.position().x())
        if idx < 0 or idx >= len(self.intervals):
            self.setToolTip("")
            return
        iv = self.intervals[idx]
        ftp = getattr(iv, "_ftp_ref", None)

        dur_m = iv.duration // 60
        dur_s = iv.duration % 60
        dur_str = f"{dur_m}m {dur_s:02}s" if dur_m else f"{dur_s}s"

        # Dohvati FTP — workout > intervals.icu profil > fallback 220
        try:
            ftp = self.parent()._intervals_ftp()
        except Exception:
            ftp = 220

        if iv.slope is not None:
            ref_w = round(iv.power_pct * ftp)
            power_str = f"⛰ Slope {iv.slope:+.1f}%  |  ref {round(iv.power_pct*100)}% FTP ({ref_w} W)"
        elif iv.type in ("ramp", "warmup", "cooldown"):
            w_start = round(iv.power_pct * ftp)
            w_end   = round(iv.power_pct_end * ftp)
            power_str = (f"Ramp {round(iv.power_pct*100)}→{round(iv.power_pct_end*100)}% FTP"
                         f"  ({w_start}→{w_end} W)")
        else:
            watts = round(iv.power_pct * ftp)
            power_str = f"{round(iv.power_pct*100)}% FTP  ({watts} W)"

        zone = ""
        pct = max(iv.power_pct, getattr(iv, "power_pct_end", iv.power_pct))
        if   pct <= 0.55: zone = "Z1 Active Recovery"
        elif pct <= 0.75: zone = "Z2 Endurance"
        elif pct <= 0.90: zone = "Z3 Tempo"
        elif pct <= 1.05: zone = "Z4 Threshold"
        elif pct <= 1.20: zone = "Z5 VO2 Max"
        elif pct <= 1.50: zone = "Z6 Anaerobic"
        else:             zone = "Z7 Neuromuscular"

        lines_tip = [
            iv.name,
            f"Trajanje: {dur_str}",
            f"Snaga: {power_str}",
            f"Zona: {zone}",
        ]
        # Kadenca — iz opisa intervala ili iz power zone (ako je postavljen)
        cad = getattr(iv, 'cadence_rpm', 0)
        if cad > 0:
            lines_tip.append(f"Kadenca: {cad} rpm")
        elif hasattr(self, '_cadence_lookup_fn'):
            cad_zone = self._cadence_lookup_fn(iv)
            if cad_zone > 0:
                lines_tip.append(f"Kadenca: ~{cad_zone} rpm (zona)")
        self.setToolTip("\n".join(lines_tip))

    def mousePressEvent(self, event):
        pass  # klik ne radi ništa — navigacija samo tipkama



class ZoneBarWidget(QWidget):
    """
    Kompaktni prikaz power ili HR zona — jedan redak po zoni:
    label | boja bar | raspon
    """

    def __init__(self, mode: str = "power"):
        super().__init__()
        self._zones: list[dict] = []
        self._time_in_zones: list[int] = []
        self._total_duration: int = 0
        self._mode = mode  # "power" ili "hr"
        self.setMinimumHeight(10)

    def set_zones(self, zones: list[dict], total_duration: int = 0):
        """zones: lista dict s poljima name, color, min_val, max_val."""
        self._zones = zones
        self._time_in_zones = [0] * len(zones)
        self._total_duration = total_duration
        self.setFixedHeight(len(zones) * 16)
        self.update()

    def update_current(self, value: float):
        """Dodaj 1 sekundu u zonu koja odgovara trenutnoj vrijednosti."""
        if not self._zones or value <= 0:
            return
        if len(self._time_in_zones) != len(self._zones):
            self._time_in_zones = [0] * len(self._zones)
        for i, z in enumerate(self._zones):
            if z.get("min_val", 0) <= value <= z.get("max_val", 99999):
                self._time_in_zones[i] += 1
                break
        self.update()

    def reset_time(self):
        self._time_in_zones = [0] * len(self._zones)
        self.update()

    def paintEvent(self, event):
        if not self._zones:
            return
        from PyQt6.QtGui import QFont
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        n = len(self._zones)
        row_h  = 16
        zone_h = row_h - 5
        fill_h = 3

        lbl_w   = 16
        range_w = 52
        bar_w   = max(6, w - lbl_w - range_w - 6)

        # Fiksni raspon za ljepši prikaz
        if self._mode == "power":
            global_min = 60    # ispod 60W nema smisla za indoor
            global_max = 600   # max za indoor
        else:  # hr
            global_min = 60    # ispod 60 bpm nema smisla
            global_max = max((z.get("max_val", 0) or 0) for z in self._zones)
        span = global_max - global_min if global_max > global_min else 1


        tiz = self._time_in_zones
        if len(tiz) != n:
            tiz = [0] * n
        denom = self._total_duration if self._total_duration > 0 else max(sum(tiz), 1)

        font = QFont()
        font.setPixelSize(8)
        painter.setFont(font)

        for i, zone in enumerate(self._zones):
            y     = i * row_h
            color = QColor(zone.get("color", "#888888"))
            name  = zone.get("name", f"Z{i+1}")
            min_v = zone.get("min_val", 0) or 0
            max_v = zone.get("max_val", 0) or 0
            bx    = lbl_w + 1

            # label
            painter.setPen(QColor("#666666"))
            painter.drawText(0, y, lbl_w, zone_h, Qt.AlignmentFlag.AlignVCenter, name)

            # gornja traka — pozicija zone, clamped na [0, bar_w]
            x_start = max(0, int(bar_w * (min_v - global_min) / span))
            x_end   = min(bar_w, int(bar_w * (max_v - global_min) / span))
            zw      = max(2, x_end - x_start)
            painter.fillRect(bx, y + 1, bar_w, zone_h - 2, QColor("#2a2a2a"))
            dim = QColor(color); dim.setAlphaF(0.4)
            painter.fillRect(bx + x_start, y + 1, zw, zone_h - 2, dim)

            # donja traka — time-in-zone, puna širina
            fy = y + zone_h + 1
            painter.fillRect(bx, fy, bar_w, fill_h, QColor("#222222"))
            if i < len(tiz) and tiz[i] > 0:
                ratio = min(tiz[i] / denom, 1.0)
                fw    = max(2, int(bar_w * ratio))
                painter.fillRect(bx, fy, fw, fill_h, color)

            # raspon — za zadnju zonu power prikaži "331+" umjesto "331-600"
            painter.setPen(QColor("#666666"))
            is_last = (i == n - 1)
            if is_last and self._mode == "power":
                range_str = f"{min_v}+"
            else:
                range_str = f"{min_v}–{max_v}"
            painter.drawText(
                lbl_w + bar_w + 3, y, range_w, zone_h,
                Qt.AlignmentFlag.AlignVCenter,
                range_str
            )


import math as _math

class ArcGaugeWidget(QWidget):
    """
    Speedometer arc gauge — zone popunjene do centra, bijela kazaljka.
    mode="power": skala 0-600W, zone po FTP postocima
    mode="hr":    skala 60-max bpm, zone po HR zonama
    """
    # Kadenca se određuje iz power zona — nema više lookup tablice po nazivu

    def __init__(self, mode: str = "power"):
        super().__init__()
        self._mode  = mode
        self._value = 0
        self._zones: list[dict] = []
        self._ftp   = 220
        self._cadence_range = (0, 0)
        self._cadence_color = "#378ADD"
        self._lamp_low    = False
        self._lamp_high   = False
        self._lamp_active = False
        self._lamp_blink  = True
        if mode == "cadence":
            self.setMinimumWidth(200)
        else:
            self.setFixedSize(300, 220)

    def set_zones(self, zones: list[dict], ftp: int = 220):
        self._zones = zones
        self._ftp   = ftp
        self.update()

    def set_value(self, value: int):
        if value != self._value:
            self._value = value
            self.update()

    def set_cadence_rpm(self, rpm: int, zone_color: str = "", tolerance: int = 5):
        """Postavi raspon kadence iz rpm vrijednosti ± tolerancija."""
        self._cadence_range = (rpm - tolerance, rpm + tolerance)
        self._cadence_color = "#378ADD"
        self.update()

    def set_cadence_range_direct(self, lo: float, hi: float, zone_color: str = ""):
        """Postavi raspon kadence direktno (za interpolaciju)."""
        self._cadence_range = (round(lo), round(hi))
        self._cadence_color = "#378ADD"
        self.update()

    def set_lamps(self, low: bool, high: bool, active: bool = True):
        """Postavi stanje lampica (samo za power gauge, slope mod)."""
        if low != self._lamp_low or high != self._lamp_high or active != self._lamp_active:
            self._lamp_low  = low
            self._lamp_high = high
            self._lamp_active = active
            self.update()

    def blink_tick(self):
        """Poziva se svakih 500ms — togglea blink state ako je lampica aktivna."""
        if self._lamp_active and (self._lamp_low or self._lamp_high):
            self._lamp_blink = not self._lamp_blink
            self.update()
        elif self._lamp_blink is False:
            self._lamp_blink = True
            self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainterPath, QFont
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        # Ostavimo prostor za broj ispod gauga
        arc_h = int(H * 0.72)
        cx, cy = W // 2, arc_h
        R = min(cx - 14, cy - 10)

        # Raspon po modu
        if self._mode == "power":
            v_min, v_max = 0, 600
        elif self._mode == "cadence":
            v_min, v_max = 0, 160
        else:  # hr
            v_min = 60
            v_max = max((z.get("max_val", 180) for z in self._zones), default=182)

        def angle(v):
            """Kut u radijanima — 0W = lijevo (180°), max = desno (0°)."""
            t = max(0.0, min(1.0, (v - v_min) / (v_max - v_min)))
            return _math.pi - t * _math.pi  # 180° → 0°

        def arc_point(a, r):
            return cx + r * _math.cos(a), cy - r * _math.sin(a)

        # Premium auto stil D — prigušeni fill + obojeni vanjski rub
        GAP = 0.009
        FILL_ALPHA   = 0.10
        STROKE_W     = max(4, int(R * 0.09))
        STROKE_ALPHA = 0.65

        zones_to_draw = self._zones if self._zones else [
            {"min_val": 0, "max_val": v_max, "color": "#2a2d35"}
        ]

        # 1. Prigušeni fill (pie do centra)
        for z in zones_to_draw:
            zmin = z.get("min_val", 0)
            zmax = z.get("max_val", v_max)
            a1 = angle(max(zmin, v_min)) - GAP
            a2 = angle(min(zmax, v_max)) + GAP
            if a1 <= a2:
                continue
            color = QColor(z.get("color", "#444444"))
            color.setAlphaF(FILL_ALPHA)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            p2 = QPainterPath()
            p2.moveTo(cx, cy)
            x1, y1 = arc_point(a1, R)
            p2.lineTo(x1, y1)
            steps = max(8, int(abs(a1 - a2) / 0.05))
            for s in range(1, steps + 1):
                a = a1 + (a2 - a1) * s / steps
                x, y = arc_point(a, R)
                p2.lineTo(x, y)
            p2.lineTo(cx, cy)
            p2.closeSubpath()
            painter.drawPath(p2)

        # 2. Obojeni vanjski rub — QPainterPath arc, gladak
        from PyQt6.QtGui import QPainterPath as _PP
        for z in zones_to_draw:
            zmin = z.get("min_val", 0)
            zmax = z.get("max_val", v_max)
            a1 = angle(max(zmin, v_min)) - GAP
            a2 = angle(min(zmax, v_max)) + GAP
            if a1 <= a2:
                continue
            color = QColor(z.get("color", "#444444"))
            color.setAlphaF(STROKE_ALPHA)
            pen = QPen(color, STROKE_W, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r_mid = R - STROKE_W // 2
            steps = max(32, int(abs(a1 - a2) / 0.02))
            arc_path = _PP()
            x0, y0 = arc_point(a1, r_mid)
            arc_path.moveTo(x0, y0)
            for s in range(1, steps + 1):
                a = a1 + (a2 - a1) * s / steps
                xp, yp = arc_point(a, r_mid)
                arc_path.lineTo(xp, yp)
            painter.drawPath(arc_path)


        # Cadence — optimalna zona obojena
        if self._mode == "cadence" and self._cadence_range and self._cadence_range != (0, 0):
            c_lo, c_hi = self._cadence_range
            a_lo = angle(max(c_lo, v_min))
            a_hi = angle(min(c_hi, v_max))
            if a_lo > a_hi:
                zone_color = QColor(self._cadence_color)
                zone_color.setAlphaF(0.12)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(zone_color)
                p_zone = QPainterPath()
                p_zone.moveTo(cx, cy)
                x1, y1 = arc_point(a_lo, R)
                p_zone.lineTo(x1, y1)
                steps = max(12, int(abs(a_lo - a_hi) / 0.04))
                for s in range(1, steps + 1):
                    a = a_lo + (a_hi - a_lo) * s / steps
                    xp, yp = arc_point(a, R)
                    p_zone.lineTo(xp, yp)
                p_zone.lineTo(cx, cy)
                p_zone.closeSubpath()
                painter.drawPath(p_zone)
                # rub zone
                zone_color2 = QColor(self._cadence_color)
                zone_color2.setAlphaF(0.75)
                pen_z = QPen(zone_color2, max(4, int(R*0.09)),
                             Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                painter.setPen(pen_z)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                r_mid = R - max(4, int(R*0.09)) // 2
                pts_z = [arc_point(a_lo + (a_hi - a_lo)*s/steps, r_mid)
                         for s in range(steps + 1)]
                p_arc = QPainterPath()
                p_arc.moveTo(*pts_z[0])
                for pt in pts_z[1:]:
                    p_arc.lineTo(*pt)
                painter.drawPath(p_arc)

        # Lampice (samo power gauge, slope mod)
        if self._mode == "power":
            lamp_r = 6
            # Plava — gore lijevo — smanji
            lx_left  = 14
            lx_right = W - 14
            ly = 14
            blink_on = self._lamp_blink
            if self._lamp_active:
                col_left  = QColor("#dd0447") if (self._lamp_low  and blink_on) else QColor("#2a0810")
                col_right = QColor("#dd0447") if (self._lamp_high and blink_on) else QColor("#2a0810")
                brd_left  = QColor("#ff2060") if (self._lamp_low  and blink_on) else QColor("#4a1520")
                brd_right = QColor("#ff2060") if (self._lamp_high and blink_on) else QColor("#4a1520")
            else:
                col_left = QColor("#2a0810"); brd_left = QColor("#4a1520")
                col_right = QColor("#2a0810"); brd_right = QColor("#4a1520")
            # Lijeva — plava (preslab)
            painter.setBrush(col_left)
            painter.setPen(QPen(brd_left, 1))
            painter.drawEllipse(lx_left - lamp_r, ly - lamp_r, lamp_r*2, lamp_r*2)
            # Desna — crvena (prejak)
            painter.setBrush(col_right)
            painter.setPen(QPen(brd_right, 1))
            painter.drawEllipse(lx_right - lamp_r, ly - lamp_r, lamp_r*2, lamp_r*2)

        # Premium pivot krug u centru
        pivot_r = max(8, int(R * 0.08))
        painter.setBrush(QColor("#0e1015"))
        painter.setPen(QPen(QColor("#2a2d35"), 1))
        painter.drawEllipse(int(cx - pivot_r), int(cy - pivot_r),
                            pivot_r * 2, pivot_r * 2)

        # Kazaljka
        if self._mode == "power":
            needle_color = QColor("#c8a84b")
        elif self._mode == "cadence":
            needle_color = QColor("#9098a8")
        else:
            needle_color = QColor("#dd0447")
        val_clamped = max(v_min, min(v_max, self._value))
        a_needle = angle(val_clamped)
        nx = cx + (R - 12) * _math.cos(a_needle)
        ny = cy - (R - 12) * _math.sin(a_needle)
        pen = QPen(needle_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(cx), int(cy), int(nx), int(ny))

        painter.setBrush(needle_color)
        painter.setPen(Qt.PenStyle.NoPen)
        dot_r = max(3, int(R * 0.04))
        painter.drawEllipse(int(cx - dot_r), int(cy - dot_r), dot_r * 2, dot_r * 2)

        # Oznake min/max

        # Broj i jedinica ispod gauga
        font_val = QFont("Courier New")
        font_val.setPixelSize(28)
        font_val.setWeight(QFont.Weight.Medium)
        painter.setFont(font_val)
        val_str = str(self._value) if self._value > 0 else "—"
        if self._mode == "power":
            val_color = QColor("#e8e0d0")
        elif self._mode == "cadence":
            val_color = QColor("#e8e0d0")
        else:
            val_color = QColor("#e8e0d0")
        painter.setPen(val_color)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(val_str)
        painter.drawText(cx - tw//2, arc_h + 30, val_str)

        font_unit = QFont()
        font_unit.setPixelSize(10)
        painter.setFont(font_unit)
        unit_map = {"power": "W", "cadence": "rpm", "hr": "bpm"}
        unit_str = unit_map.get(self._mode, "")
        if self._mode == "power":    u_color = QColor("#c8a84b")
        elif self._mode == "cadence": u_color = QColor("#9098a8")
        else:                         u_color = QColor("#dd0447")
        painter.setPen(u_color)
        fm2 = painter.fontMetrics()
        uw = fm2.horizontalAdvance(unit_str)
        painter.drawText(cx - uw//2, arc_h + 44, unit_str)


class SlopePanelWidget(QWidget):
    """
    Srednji panel — ERG/SLOPE mod indikator, strelice za slope feedback.
    """
    def __init__(self):
        super().__init__()
        self._mode      = "ERG"   # "ERG" ili "SLOPE"
        self._ref_power = None    # int W ili None
        self._cur_power = 0
        self._tolerance = 15      # W
        self.setMinimumWidth(100)

    def set_mode(self, mode: str):
        self._mode = mode
        self.update()

    def set_ref(self, ref_power):
        self._ref_power = ref_power
        self.update()

    def set_power(self, power: int):
        if power != self._cur_power:
            self._cur_power = power
            self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainterPath, QFont
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W // 2, H // 2

        font_big = QFont()
        font_big.setPixelSize(14)
        font_sm = QFont()
        font_sm.setPixelSize(10)

        # Ako nema ref ili nije slope mod — samo tekst
        if self._mode != "SLOPE" or self._ref_power is None:
            painter.setPen(QColor("#555555"))
            painter.setFont(font_big)
            painter.drawText(
                0, 0, W, H,
                Qt.AlignmentFlag.AlignCenter,
                self._mode
            )
            return

        diff = self._ref_power - self._cur_power  # pozitivno = treba jače
        in_zone = abs(diff) <= self._tolerance

        if in_zone:
            # Zeleni krug — manji i popunjen
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#009e80"))
            r = min(W, H) // 4 - 4
            painter.drawEllipse(cx - r, cy - r, 2*r, 2*r)
        else:
            # Strelica
            going_up = diff > 0  # treba jače = strelica gore
            color = QColor("#dd0447") if going_up else QColor("#378ADD")
            aw = min(W, 80)
            ah = min(H - 60, 80)
            ax = cx - aw // 2
            ay = cy - ah // 2

            path = QPainterPath()
            if going_up:
                path.moveTo(cx,        ay)
                path.lineTo(cx + aw//2, ay + ah*0.5)
                path.lineTo(cx + aw//4, ay + ah*0.5)
                path.lineTo(cx + aw//4, ay + ah)
                path.lineTo(cx - aw//4, ay + ah)
                path.lineTo(cx - aw//4, ay + ah*0.5)
                path.lineTo(cx - aw//2, ay + ah*0.5)
            else:
                path.moveTo(cx,        ay + ah)
                path.lineTo(cx + aw//2, ay + ah*0.5)
                path.lineTo(cx + aw//4, ay + ah*0.5)
                path.lineTo(cx + aw//4, ay)
                path.lineTo(cx - aw//4, ay)
                path.lineTo(cx - aw//4, ay + ah*0.5)
                path.lineTo(cx - aw//2, ay + ah*0.5)
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(path)

            # Razlika u W
            painter.setPen(color)
            painter.setFont(font_big)
            painter.drawText(
                0, ay + ah + 6, W, 20,
                Qt.AlignmentFlag.AlignCenter,
                f"{abs(diff)} W"
            )

        # Referentna snaga
        painter.setPen(QColor("#444444"))
        painter.setFont(font_sm)
        painter.drawText(
            0, H - 18, W, 16,
            Qt.AlignmentFlag.AlignCenter,
            f"ref {self._ref_power} W  ±{self._tolerance} W"
        )

class GradeWidget(QWidget):
    """
    Bubble level inklinometar za prikaz i ručnu korekciju nagiba.
    - Skala: -10% do +10%, korak 0.5%
    - U slobodnom modu: direktna kontrola nagiba
    - U slope workout modu: prikazuje nagib intervala + ručna korekcija
    - Kad se interval promijeni: korekcija se resetira na 0
    """

    # signal prema MainWindow — novi željeni nagib
    grade_changed = pyqtSignal(float)

    GRADE_MIN = -10.0
    GRADE_MAX =  10.0
    STEP      =  0.5

    def __init__(self):
        super().__init__()
        self._base_grade: float = 0.0      # nagib iz workota ili slobodnog moda
        self._correction: float = 0.0      # ručna korekcija korisnika
        self._last_interval_idx: int = -1  # za detekciju promjene intervala
        self.setFixedHeight(74)
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(4)

        # bubble canvas
        self._canvas = _BubbleCanvas(self)
        self._canvas.setFixedHeight(32)
        lay.addWidget(self._canvas)

        # tipke + vrijednost
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._btn_minus = QPushButton("−")
        self._btn_minus.setFixedSize(28, 28)
        self._btn_minus.clicked.connect(self._on_minus)

        self._val_lbl = QLabel("0.0%")
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val_lbl.setStyleSheet(
            "font-family: 'Courier New'; font-size: 15px; font-weight: 500; color: #e8e0d0;"
        )

        self._btn_plus = QPushButton("+")
        self._btn_plus.setFixedSize(28, 28)
        self._btn_plus.clicked.connect(self._on_plus)

        self._corr_lbl = QLabel("")
        self._corr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._corr_lbl.setStyleSheet("font-size: 9px; color: #505868;")

        btn_row.addWidget(self._btn_minus)
        btn_row.addWidget(self._val_lbl, stretch=1)
        btn_row.addWidget(self._btn_plus)
        lay.addLayout(btn_row)
        lay.addWidget(self._corr_lbl)

        self._refresh()

    def set_base_grade(self, grade: float, interval_idx: int = -1):
        """Postavi bazni nagib (iz workota ili slobodnog moda).
        Ako se interval promijenio, resetiraj korekciju."""
        if interval_idx != self._last_interval_idx and interval_idx >= 0:
            self._correction = 0.0
            self._last_interval_idx = interval_idx
        self._base_grade = grade
        self._refresh()

    def _effective_grade(self) -> float:
        return max(self.GRADE_MIN, min(self.GRADE_MAX,
                   round((self._base_grade + self._correction) * 10) / 10))

    def _on_minus(self):
        self._correction = round((self._correction - self.STEP) * 10) / 10
        # ne dozvoli pad ispod minimuma
        if self._effective_grade() <= self.GRADE_MIN:
            self._correction = round((self.GRADE_MIN - self._base_grade) * 10) / 10
        self._refresh()
        self.grade_changed.emit(self._effective_grade())

    def _on_plus(self):
        self._correction = round((self._correction + self.STEP) * 10) / 10
        if self._effective_grade() >= self.GRADE_MAX:
            self._correction = round((self.GRADE_MAX - self._base_grade) * 10) / 10
        self._refresh()
        self.grade_changed.emit(self._effective_grade())

    def _refresh(self):
        g = self._effective_grade()
        sign = "+" if g >= 0 else ""
        self._val_lbl.setText(f"{sign}{g:.1f}%")
        self._canvas.set_grade(g)
        # korekcija label — prikaži samo kad != 0
        if abs(self._correction) > 0.01:
            csign = "+" if self._correction > 0 else ""
            self._corr_lbl.setText(f"baza {self._base_grade:+.1f}%  korekcija {csign}{self._correction:.1f}%")
        else:
            self._corr_lbl.setText("")


class _BubbleCanvas(QWidget):
    """Crtanje bubble level trake."""

    GRADE_MIN = -10.0
    GRADE_MAX =  10.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grade: float = 0.0

    def set_grade(self, grade: float):
        if grade != self._grade:
            self._grade = grade
            self.update()

    def paintEvent(self, event):
        import math as _m
        from PyQt6.QtGui import QFont
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        pad = 14          # prostor za oznake na rubovima
        track_y = H // 2
        track_h = 8
        track_x = pad
        track_w = W - 2 * pad

        # track pozadina
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1e2230"))
        painter.drawRoundedRect(track_x, track_y - track_h // 2,
                                track_w, track_h, track_h // 2, track_h // 2)

        # sredinska crta (0%)
        mid_x = track_x + track_w // 2
        painter.setPen(QPen(QColor("#3a4050"), 1))
        painter.drawLine(mid_x, track_y - track_h // 2 - 2,
                         mid_x, track_y + track_h // 2 + 2)

        # pozicija mjehurića
        t = (self._grade - self.GRADE_MIN) / (self.GRADE_MAX - self.GRADE_MIN)
        bx = int(track_x + t * track_w)
        bubble_r = 13

        # boja prema nagibu
        abs_g = abs(self._grade)
        if abs_g < 0.3:
            bubble_color = QColor("#009e80")   # zelena — ravno
            border_color = QColor("#007060")
        elif self._grade > 0:
            # uzbrdo — crvena, jača kako raste
            intensity = min(abs_g / 10.0, 1.0)
            r = int(180 + intensity * 75)
            bubble_color = QColor(r, 60, 60)
            border_color = QColor("#dd0447")
        else:
            # nizbrdo — plava
            intensity = min(abs_g / 10.0, 1.0)
            b = int(160 + intensity * 80)
            bubble_color = QColor(50, 100, b)
            border_color = QColor("#378ADD")

        # mjehurić
        painter.setPen(QPen(border_color, 2))
        painter.setBrush(bubble_color)
        painter.drawEllipse(bx - bubble_r, track_y - bubble_r,
                            bubble_r * 2, bubble_r * 2)

        # oznake rubova
        font = QFont()
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(QColor("#3a4050"))
        painter.drawText(0, 0, pad, H, Qt.AlignmentFlag.AlignCenter, "-10")
        painter.drawText(W - pad, 0, pad, H, Qt.AlignmentFlag.AlignCenter, "+10")


class PowerHrChart(QWidget):
    """
    Rolling graf snage (plava) i HR (crvena).
    Uvijek scrolla zdesna nalijevo — preskakanje intervala ne utječe na crtanje.
    """
    WINDOW = 300  # sekundi prikazano u prozoru

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(80)
        self._power_data: list[int] = []
        self._hr_data: list[int] = []

    def add_point(self, power: int, hr: int):
        self._power_data.append(max(0, power))
        self._hr_data.append(max(0, hr))
        # ograniči memoriju — čuvamo samo WINDOW*3 zadnjih točaka
        cap = self.WINDOW * 3
        if len(self._power_data) > cap:
            self._power_data = self._power_data[-cap:]
            self._hr_data    = self._hr_data[-cap:]
        self.update()

    def reset(self):
        self._power_data = []
        self._hr_data = []
        self.update()

    # compat stubs — više nisu potrebni ali mogu se zvati
    def set_workout(self, *a, **kw): pass
    def clear_workout(self): self.reset()
    def seek(self, *a, **kw): pass
    def set_bar_x_fraction(self, *a, **kw): pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        pad = 4

        # referentne linije
        painter.setPen(QPen(QColor("#333333"), 1))
        for watts in range(50, 451, 50):
            y = int(h - pad - (watts / 450) * (h - 2 * pad))
            painter.drawLine(pad, y, w - pad, y)

        n = len(self._power_data)
        if n < 2:
            return

        # prikaži zadnjih WINDOW točaka, poravnato desno
        win = self.WINDOW
        start = max(0, n - win)
        pw  = self._power_data[start:]
        hr_ = self._hr_data[start:]
        m   = len(pw)
        if m < 2:
            return

        def sx(i):  return pad + (i / (win - 1)) * (w - 2 * pad)
        def sp(v):  return h - pad - (max(0, min(450, v)) / 450) * (h - 2 * pad)
        def shr(v): return h - pad - (max(0, min(200, v) - 60) / 140) * (h - 2 * pad)

        # offset: ako imamo manje od WINDOW točaka, crtamo od desna
        offset = win - m

        # HR — crvena
        painter.setPen(QPen(QColor("#A32D2D"), 1.5))
        for i in range(1, m):
            if hr_[i] > 0 and hr_[i-1] > 0:
                painter.drawLine(int(sx(offset+i-1)), int(shr(hr_[i-1])),
                                 int(sx(offset+i)),   int(shr(hr_[i])))

        # Snaga — plava
        painter.setPen(QPen(QColor("#185FA5"), 1.5))
        for i in range(1, m):
            if pw[i] > 0 or pw[i-1] > 0:
                painter.drawLine(int(sx(offset+i-1)), int(sp(pw[i-1])),
                                 int(sx(offset+i)),   int(sp(pw[i])))


class MainWindow(QMainWindow):

    # thread-safe signali za komunikaciju asyncio → Qt thread
    _metrics_signal = pyqtSignal(object)
    _state_signal = pyqtSignal(object)
    _hr_signal = pyqtSignal(int)
    _hr_connected_signal = pyqtSignal(bool)
    _hr_name_signal = pyqtSignal(bool, str)  # (connected, name)
    _intervals_done_signal = pyqtSignal(object, object)  # (athlete_dict, workouts_list)
    _intervals_error_signal = pyqtSignal(str)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_if_tss_width)

    def _sync_if_tss_width(self):
        try:
            w = self.tc_clock.width()
            if w > 10:
                self._stats_right_ref.setFixedWidth(w - 14)
        except Exception:
            pass

    def paintEvent(self, event):
        """Background slika kao podloga."""
        from PyQt6.QtGui import QPixmap
        import os
        painter = QPainter(self)
        bg_path = os.path.join(os.path.dirname(__file__), "background.png")
        if not hasattr(self, "_bg_pixmap"):
            self._bg_pixmap = QPixmap(bg_path)
        if not self._bg_pixmap.isNull():
            painter.drawPixmap(0, 0, self.width(), self.height(), self._bg_pixmap)
        else:
            painter.fillRect(0, 0, self.width(), self.height(), QColor("#0a0c10"))

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Trainer")
        self.setMinimumSize(900, 620)

        self.player = WorkoutPlayer()
        self.mode = TrainerMode.ERG
        self.trainer_state = ConnectionState.DISCONNECTED
        self.hr_state = ConnectionState.DISCONNECTED
        self._trainer = None
        self._hr_monitor = None
        self._trainer_name = "Trenažer"
        self._trainer_display_name = ""
        self._hr_display_name = ""
        self._dark_mode = True
        self._int_hr_sum = 0
        self._int_hr_cnt = 0
        self._intervals_athlete_id = ""
        self._intervals_api_key = ""
        self._intervals_workouts_today: list = []
        self._zone_color_tick = 0  # brojač za osvježavanje boja zona
        self._prev_interval_idx = 0
        self._cadence_interpolating = False
        # Blink timer za lampice — 500ms
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._on_blink_tick)
        self._blink_timer.start(500)
        from intervals.client import load_config, load_local_athlete
        _cfg = load_config()
        self._tolerance = int(_cfg.get("tolerance", 15))

        self._setup_ui()
        self._setup_chart()
        self._setup_timer()
        self._apply_stylesheet()

        self._metrics_signal.connect(self._on_metrics_received)
        self._state_signal.connect(self._on_state_received)
        self._hr_signal.connect(self._on_hr_received)
        self._hr_connected_signal.connect(lambda c: self._set_hr_ui(c, "Spoji"))
        self._hr_name_signal.connect(self._set_hr_ui)
        self._intervals_done_signal.connect(self._intervals_on_done)
        self._intervals_error_signal.connect(self._intervals_on_error)

        local = load_local_athlete()
        if local:
            self._apply_local_athlete(local)

        cfg = load_config()
        if cfg.get("athlete_id") and cfg.get("api_key"):
            self._intervals_athlete_id = cfg["athlete_id"]
            self._intervals_api_key = cfg["api_key"]
            self._intervals_fetch_start()

    def _zone_color_for(self, value: float, zones: list) -> str | None:
        """Vrati hex boju zone za danu vrijednost (watts ili bpm)."""
        if not zones or value <= 0:
            return None
        for z in zones:
            if z.get("min_val", 0) <= value <= z.get("max_val", 99999):
                return z.get("color")
        return None

    def _apply_zone_colors(self, power: float, hr: float):
        """Zone boje su sada direktno na arc gauge kazaljkama — ovdje samo pass."""
        pass

    def _intervals_ftp(self) -> int:
        """Vrati FTP iz učitanog workota ili athlete profila."""
        if self.player.workout:
            return self.player.workout.ftp
        try:
            return int(self.topbar_athlete_lbl.text().split("FTP:")[1].split("W")[0].strip())
        except Exception:
            return 220

    def _on_show_format_help(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget, QPushButton
        from PyQt6.QtGui import QFont

        dlg = QDialog(self)
        dlg.setWindowTitle("intervals.icu — workout format")
        dlg.setMinimumWidth(520)
        dlg.setMinimumHeight(580)

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(16, 16, 16, 8)
        lay.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll, stretch=1)

        def section(title, body):
            t = QLabel(title)
            t.setStyleSheet("font-size: 12px; font-weight: 600; color: #aaa; margin-top: 4px;")
            lay.addWidget(t)
            b = QLabel(body)
            b.setFont(QFont("Courier New", 9))
            b.setStyleSheet("background: #1a1a1a; color: #d0d0d0; padding: 8px; border-radius: 4px;")
            b.setWordWrap(True)
            b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lay.addWidget(b)

        section("Steady State (ERG — konstantna snaga)",
"""- 10m 75% FTP @85-95rpm
- 20m 88% FTP
- 5m 55% FTP Recovery""")

        section("Ramp (postepeni porast ili pad)",
"""- 15m Ramp 60-85% FTP WarmUp
- 10m Ramp 80-50% FTP CoolDown""")

        section("Intervali s ponavljanjem",
"""3x
- 8m 105% FTP VO2 Max
- 4m 55% FTP Recovery

5x
- 30s 130% FTP Sprint
- 30s 50% FTP""")

        section("Slope mod (nagib terena — #X.X% SLOPE#)",
"""- 20m 75% FTP #2.0% SLOPE#
- 5m 60% FTP Recovery

3x
- 15m 80% FTP #3.5% SLOPE# Climb
- 5m 55% FTP Recovery""")

        section("Kombinirani trening",
"""- 15m Ramp 55-75% FTP WarmUp

3x
- 5m 95% FTP Threshold
- 3m 55% FTP Recovery
- 3m 105% FTP VO2 Max
- 2m 50% FTP

2x
- 10m 88% FTP #1.5% SLOPE# SweetSpot
- 5m 60% FTP Recovery

- 10m Ramp 70-45% FTP CoolDown""")

        section("Napomene",
"""• Trajanje: 30s, 5m, 1h, 1h30m
• Snaga: 75% FTP  ili  220w  ili  220W
• Nagib: #2.0% SLOPE# u text tagu
• Naziv koraka: tekst na kraju retka
• Repeticije: samo broj i 'x' u retku (npr. 3x)
• FTP se čita iz intervals.icu profila""")

        lay.addStretch()

        close_btn = QPushButton("Zatvori")
        close_btn.clicked.connect(dlg.accept)
        outer.addWidget(close_btn)
        dlg.exec()

    def closeEvent(self, event):
        """Pri zatvaranju prozora pošalji slope 0% trenažeru."""
        if self._trainer and self._trainer.state == ConnectionState.CONNECTED:
            run_async(self._trainer.set_grade(0.0))
        event.accept()

    # ------------------------------------------------------------------ UI

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addLayout(self._build_left_panel(), stretch=1)
        body.addWidget(self._build_right_panel())
        root.addLayout(body, stretch=1)

        root.addWidget(self._build_transport_bar())

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(40)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 14, 0)

        self.title_lbl = QLabel("Smart Trainer")
        self.title_lbl.setObjectName("appTitle")

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDotDisconnected")

        self.status_lbl = QLabel("Devices")
        self.status_lbl.setObjectName("statusLabel")

        from version import VERSION
        version_lbl = QLabel(VERSION)
        version_lbl.setStyleSheet("color: #3a4050; font-size: 10px;")

        lay.addWidget(self.title_lbl)
        lay.addWidget(self.status_dot)
        lay.addWidget(self.status_lbl)
        lay.addStretch()

        # intervals.icu athlete info u topbaru
        self.topbar_athlete_lbl = QLabel("")
        self.topbar_athlete_lbl.setStyleSheet("font-size: 11px; color: #7a8090;")
        self.topbar_today_lbl = QLabel("")  # zadržavamo referencu, ali ne prikazujemo
        lay.addWidget(self.topbar_athlete_lbl)
        lay.addSpacing(12)
        lay.addWidget(version_lbl)
        return bar

    def _build_left_panel(self) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # metrike — gornji red
        grid = QGridLayout()
        grid.setSpacing(5)
        # Samo drugi red — postaje prvi, s gold borderom
        self.mc_avg_pw  = MetricCard("Int. avg snaga", "W")
        self.mc_target  = MetricCard("Zadana snaga",   "W")
        self.mc_avg_hr  = MetricCard("Int. avg puls",  "bpm")
        for col, mc in enumerate([self.mc_avg_pw, self.mc_target, self.mc_avg_hr]):
            grid.addWidget(mc, 0, col)
        lay.addLayout(grid)

        # chart — iste proporcije kao workout bar, bez Y osi
        # Gauge panel — arc indikatori i slope panel
        gauge_row = QWidget()
        gauge_row.setObjectName("card")
        gauge_lay = QHBoxLayout(gauge_row)
        gauge_lay.setContentsMargins(8, 8, 8, 8)
        gauge_lay.setSpacing(8)

        self.power_gauge   = ArcGaugeWidget(mode="power")
        self.cadence_gauge = ArcGaugeWidget(mode="cadence")
        self.hr_gauge      = ArcGaugeWidget(mode="hr")

        gauge_lay.addWidget(self.power_gauge)
        gauge_lay.addWidget(self.cadence_gauge, stretch=1)
        gauge_lay.addWidget(self.hr_gauge)

        lay.addWidget(gauge_row)

        # Compat stub — chart_widget pozivi ne pucaju
        self.chart_widget = PowerHrChart()

        # workout interval prikaz
        wo_frame = QFrame()
        wo_frame.setObjectName("card")
        wo_layout = QVBoxLayout(wo_frame)
        wo_layout.setContentsMargins(10, 8, 10, 8)
        wo_layout.setSpacing(4)

        wo_top = QHBoxLayout()
        self.workout_name_lbl = QLabel("—")
        self.workout_name_lbl.setObjectName("workoutName")
        self.workout_type_badge = QLabel("")
        self.workout_type_badge.setObjectName("badgeNeutral")
        # Naziv + detalji trenutnog intervala — centar
        # Tri nevidljive ćelije — iste proporcije kao gauge red (power | cadence | hr)
        # Lijevo: naziv treninga
        left_cell = QWidget()
        left_lay = QVBoxLayout(left_cell)
        left_lay.setContentsMargins(4, 0, 4, 0)
        left_lay.setSpacing(0)
        left_lay.addWidget(self.workout_name_lbl)

        # Sredina: naziv + detalji trenutnog intervala — centrirani
        mid_cell = QWidget()
        mid_lay = QVBoxLayout(mid_cell)
        mid_lay.setContentsMargins(4, 0, 4, 0)
        mid_lay.setSpacing(1)
        self.cur_int_center_lbl = QLabel("")
        self.cur_int_center_lbl.setObjectName("workoutName")
        self.cur_int_center_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cur_int_detail_center_lbl = QLabel("")
        self.cur_int_detail_center_lbl.setStyleSheet("font-size: 10px; color: #505868;")
        self.cur_int_detail_center_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mid_lay.addWidget(self.cur_int_center_lbl)
        mid_lay.addWidget(self.cur_int_detail_center_lbl)

        # Desno: badge vrste koraka — desno poravnato
        right_cell = QWidget()
        right_lay = QVBoxLayout(right_cell)
        right_lay.setContentsMargins(4, 0, 4, 0)
        right_lay.setSpacing(0)
        right_lay.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.workout_type_badge.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        right_lay.addWidget(self.workout_type_badge)

        wo_top.addWidget(left_cell,  stretch=2)
        wo_top.addWidget(mid_cell,   stretch=3)
        wo_top.addWidget(right_cell, stretch=2)
        wo_layout.addLayout(wo_top)

        self.interval_bar = IntervalBar([])
        self.interval_bar.clicked.connect(self._on_interval_clicked)
        wo_layout.addWidget(self.interval_bar, stretch=1)

        self.time_axis = TimeAxisWidget()
        wo_layout.addWidget(self.time_axis)

        # Stat bar — isti grid kao timegrid ispod (4 col), lampice=col 0-2, IF/TSS=col 3
        wo_stats = QHBoxLayout()
        wo_stats.setSpacing(5)
        wo_stats.setContentsMargins(0, 2, 0, 2)

        # Lijevo: lampice intervala (stretch=3)
        self.interval_dots = IntervalDotsWidget()
        wo_stats.addWidget(self.interval_dots, stretch=1)

        # Desno: IF i TSS (stretch=1)
        stats_right = QWidget()
        stats_right.setObjectName("ftpBox")
        from PyQt6.QtWidgets import QSizePolicy as _SP
        stats_right.setSizePolicy(_SP.Policy.Preferred, _SP.Policy.Preferred)
        self._stats_right = stats_right  # referenca za resize
        sr_lay = QHBoxLayout(stats_right)
        sr_lay.setContentsMargins(0, 0, 0, 0)
        sr_lay.setSpacing(0)

        if_cell = QWidget()
        if_lay = QVBoxLayout(if_cell)
        if_lay.setContentsMargins(4, 2, 4, 2)
        self.lbl_if = QLabel("IF: —")
        self.lbl_if.setObjectName("statLabel")
        self.lbl_if.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if_lay.addWidget(self.lbl_if)

        tss_cell = QWidget()
        tss_lay = QVBoxLayout(tss_cell)
        tss_lay.setContentsMargins(4, 2, 4, 2)
        self.lbl_tss = QLabel("TSS: —")
        self.lbl_tss.setObjectName("statLabel")
        self.lbl_tss.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tss_lay.addWidget(self.lbl_tss)

        sr_lay.addWidget(if_cell, stretch=1)
        sr_lay.addWidget(tss_cell, stretch=1)
        self.lbl_if.setToolTip(
            "<table style='border-collapse:collapse;font-size:12px'>"
            "<tr><th style='padding:3px 8px;text-align:left;color:#c8a84b'>IF</th>"
            "<th style='padding:3px 8px;text-align:left;color:#c8a84b'>Tip treninga</th></tr>"
            "<tr><td style='padding:2px 8px'>&lt; 0.75</td><td style='padding:2px 8px;color:#009e80'>Lagano</td></tr>"
            "<tr><td style='padding:2px 8px'>0.75 – 0.85</td><td style='padding:2px 8px;color:#009e00'>Endurance</td></tr>"
            "<tr><td style='padding:2px 8px'>0.85 – 0.95</td><td style='padding:2px 8px;color:#ffcb0e'>Tempo / Sweet Spot</td></tr>"
            "<tr><td style='padding:2px 8px'>0.95 – 1.05</td><td style='padding:2px 8px;color:#ff7f0e'>Threshold</td></tr>"
            "<tr><td style='padding:2px 8px'>&gt; 1.05</td><td style='padding:2px 8px;color:#dd0447'>VO2 / Anaerobno</td></tr>"
            "</table>"
        )
        self.lbl_tss.setToolTip(
            "<table style='border-collapse:collapse;font-size:12px'>"
            "<tr><th style='padding:3px 8px;text-align:left;color:#c8a84b'>TSS</th>"
            "<th style='padding:3px 8px;text-align:left;color:#c8a84b'>Opterećenje</th></tr>"
            "<tr><td style='padding:2px 8px'>&lt; 50</td><td style='padding:2px 8px;color:#009e80'>Lagano</td></tr>"
            "<tr><td style='padding:2px 8px'>50 – 100</td><td style='padding:2px 8px;color:#009e00'>Srednje</td></tr>"
            "<tr><td style='padding:2px 8px'>100 – 150</td><td style='padding:2px 8px;color:#ffcb0e'>Teško</td></tr>"
            "<tr><td style='padding:2px 8px'>150 – 300</td><td style='padding:2px 8px;color:#ff7f0e'>Jako teško</td></tr>"
            "<tr><td style='padding:2px 8px'>300+</td><td style='padding:2px 8px;color:#dd0447'>Brutalno</td></tr>"
            "</table>"
        )

        wo_stats.addWidget(stats_right, stretch=1)
        self._stats_right_ref = stats_right

        # Zadržimo lbl_cur_int kao stub da ne pucaju stari setText pozivi
        self.lbl_cur_int = QLabel("")
        wo_layout.addLayout(wo_stats)
        lay.addWidget(wo_frame, stretch=1)
        self.wo_frame_ref = wo_frame

        # timegrid
        tg = QGridLayout()
        tg.setSpacing(5)
        self.tc_total      = MetricCard("Ukupno", "")
        self.tc_int_elapsed = MetricCard("Int. vrijeme", "")
        self.tc_intrem     = MetricCard("Do kraja int.", "")
        self.tc_rem        = MetricCard("Do kraja", "")
        self.tc_clock      = MetricCard("Vrijeme", "")
        for col, tc in enumerate([self.tc_total, self.tc_int_elapsed, self.tc_intrem, self.tc_rem, self.tc_clock]):
            tg.addWidget(tc, 0, col)
        lay.addLayout(tg)

        return lay

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("rightPanel")
        panel.setFixedWidth(220)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # mod
        mode_row = QHBoxLayout()
        self.btn_erg = QPushButton("ERG")
        self.btn_erg.setObjectName("modeActive")
        self.btn_erg.clicked.connect(lambda: self._set_mode(TrainerMode.ERG))
        self.btn_sim = QPushButton("Slope")
        self.btn_sim.setObjectName("modeInactive")
        self.btn_sim.clicked.connect(lambda: self._set_mode(TrainerMode.SIMULATION))
        mode_row.addWidget(self.btn_erg)
        mode_row.addWidget(self.btn_sim)
        lay.addLayout(mode_row)

        # slobodni kontroler (bez workota) — default Slope 0%
        self.free_ctrl = QFrame()
        fc_lay = QVBoxLayout(self.free_ctrl)
        fc_lay.setContentsMargins(0, 0, 0, 0)
        fc_lay.setSpacing(4)
        ctrl_row = QHBoxLayout()
        self.free_ctrl_lbl = QLabel("Nagib")
        self.free_ctrl_val = QLabel("0.0 %")
        self.free_ctrl_val.setObjectName("ctrlVal")
        ctrl_row.addWidget(self.free_ctrl_lbl)
        ctrl_row.addStretch()
        ctrl_row.addWidget(self.free_ctrl_val)
        fc_lay.addLayout(ctrl_row)
        self.free_slider = QSlider(Qt.Orientation.Horizontal)
        self.free_slider.setRange(-100, 200)
        self.free_slider.setValue(0)
        self._slider_user_action = False  # true samo kad korisnik dodirne slider
        self.free_slider.sliderPressed.connect(lambda: setattr(self, '_slider_user_action', True))
        self.free_slider.sliderMoved.connect(self._on_free_slider_moved)
        self.free_slider.valueChanged.connect(self._on_free_slider_moved)
        self.free_slider.sliderReleased.connect(self._on_free_slider_released)
        # klik na track (bez drag) — sliderReleased se okida ali _slider_user_action nije True
        _orig = self.free_slider.mouseReleaseEvent
        def _mouse_release(e):
            self._slider_user_action = True
            _orig(e)
            self._on_free_slider_released()
            self._slider_user_action = False
        self.free_slider.mouseReleaseEvent = _mouse_release
        fc_lay.addWidget(self.free_slider)
        lay.addWidget(self.free_ctrl)

        # workout info (vidljivo kad je workout učitan)
        self.workout_ctrl = QFrame()
        self.workout_ctrl.setVisible(False)
        wc_lay = QVBoxLayout(self.workout_ctrl)
        wc_lay.setContentsMargins(0, 0, 0, 0)
        wc_lay.setSpacing(4)
        self.unload_btn = QPushButton("Ukloni workout")
        self.unload_btn.clicked.connect(self._on_unload_workout)
        self.unload_btn.setVisible(False)
        wc_lay.addWidget(self.unload_btn)
        lay.addWidget(self.workout_ctrl)

        # BLE uređaji
        self.trainer_dev_row = self._device_row("Trenažer", "Spoji", warning=False)
        self.trainer_dev_row.setCursor(Qt.CursorShape.PointingHandCursor)
        self.trainer_dev_row.mousePressEvent = lambda e: self._on_connect_trainer()
        self.hr_dev_row = self._device_row("Pulsmetar", "Spoji", warning=False)
        self.hr_dev_row.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hr_dev_row.mousePressEvent = lambda e: self._on_connect_hr()
        self._trainer_tag = self.trainer_dev_row.findChildren(QLabel)[-1]
        self._hr_tag = self.hr_dev_row.findChildren(QLabel)[-1]
        lay.addWidget(self.trainer_dev_row)
        lay.addWidget(self.hr_dev_row)

        # intervals.icu — dvije odvojene kutije za zone

        # Power zone kutija
        pw_frame = QFrame()
        pw_frame.setObjectName("ftpBox")
        pw_lay = QVBoxLayout(pw_frame)
        pw_lay.setContentsMargins(6, 4, 6, 4)
        pw_lay.setSpacing(2)
        pw_title = QLabel("POWER")
        pw_title.setStyleSheet("font-size: 9px; color: #3a4050; letter-spacing: 2px;")
        self.power_zone_bar = ZoneBarWidget(mode="power")
        pw_lay.addWidget(pw_title)
        pw_lay.addWidget(self.power_zone_bar)
        lay.addWidget(pw_frame)

        # HR zone kutija
        hr_frame = QFrame()
        hr_frame.setObjectName("ftpBox")
        hr_lay = QVBoxLayout(hr_frame)
        hr_lay.setContentsMargins(6, 4, 6, 4)
        hr_lay.setSpacing(2)
        hr_title = QLabel("HR")
        hr_title.setStyleSheet("font-size: 9px; color: #3a4050; letter-spacing: 2px;")
        self.hr_zone_bar = ZoneBarWidget(mode="hr")
        hr_lay.addWidget(hr_title)
        hr_lay.addWidget(self.hr_zone_bar)
        lay.addWidget(hr_frame)

        # Nagib — bubble level inklinometar (vidljiv samo u workout modu)
        self._grade_frame = QFrame()
        self._grade_frame.setObjectName("ftpBox")
        grade_lay = QVBoxLayout(self._grade_frame)
        grade_lay.setContentsMargins(6, 4, 6, 4)
        grade_lay.setSpacing(2)
        grade_title = QLabel("NAGIB")
        grade_title.setStyleSheet("font-size: 9px; color: #3a4050; letter-spacing: 2px;")
        self.grade_widget = GradeWidget()
        self.grade_widget.grade_changed.connect(self._on_grade_widget_changed)
        grade_lay.addWidget(grade_title)
        grade_lay.addWidget(self.grade_widget)
        self._grade_frame.setVisible(False)  # sakriven dok nema workota
        lay.addWidget(self._grade_frame)

        intervals_btn_row = QHBoxLayout()
        self.intervals_connect_btn = QPushButton("Postavke ↗")
        self.intervals_connect_btn.setStyleSheet("font-size: 11px;")
        self.intervals_connect_btn.clicked.connect(self._on_intervals_connect)
        self.intervals_today_btn = QPushButton("Danas")
        self.intervals_today_btn.setStyleSheet("font-size: 11px;")
        self.intervals_today_btn.setEnabled(False)
        self.intervals_today_btn.setVisible(True)
        self.intervals_today_btn.clicked.connect(self._on_intervals_today)
        intervals_btn_row.addWidget(self.intervals_connect_btn)
        intervals_btn_row.addWidget(self.intervals_today_btn)
        lay.addLayout(intervals_btn_row)

        lay.addStretch()


        load_row = QHBoxLayout()
        self.load_btn = QPushButton("Učitaj ↗")
        self.load_btn.clicked.connect(self._on_load_workout)
        self.enter_btn = QPushButton("Unesi")
        self.enter_btn.clicked.connect(self._on_enter_from_btn)
        load_row.addWidget(self.load_btn)
        load_row.addWidget(self.enter_btn)
        lay.addLayout(load_row)

        self.unload_btn2 = QPushButton("Ukloni workout")
        self.unload_btn2.clicked.connect(self._on_unload_workout)
        self.unload_btn2.setVisible(False)
        lay.addWidget(self.unload_btn2)



        return panel

    def _build_transport_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("transport")
        bar.setFixedHeight(48)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(5)

        self.btn_prev  = QPushButton("⏮")
        self.btn_play  = QPushButton("▶")
        self.btn_next  = QPushButton("⏭")
        self.btn_stop  = QPushButton("⏹")

        self.btn_prev.setFixedSize(34, 34)
        self.btn_play.setFixedSize(36, 36)
        self.btn_next.setFixedSize(34, 34)
        self.btn_stop.setFixedSize(34, 34)

        self.btn_play.setObjectName("playBtn")
        self.btn_stop.setObjectName("stopBtn")

        self.btn_prev.clicked.connect(self._on_prev)
        self.btn_play.clicked.connect(self._on_play_pause)
        self.btn_next.clicked.connect(self._on_next)
        self.btn_stop.clicked.connect(self._on_stop)

        self.timer_lbl = QLabel("00:00")
        self.timer_lbl.setObjectName("timerLabel")
        self.timer_lbl.setFixedWidth(48)

        self.progress_bar = QFrame()
        self.progress_bar.setObjectName("progressBg")
        self.progress_bar.setFixedHeight(4)
        self.progress_fill = QFrame(self.progress_bar)
        self.progress_fill.setObjectName("progressFill")
        self.progress_fill.setFixedHeight(4)
        self.progress_fill.setFixedWidth(0)

        self.total_lbl = QLabel("—")
        self.total_lbl.setObjectName("statusLabel")

        self.btn_minus = QPushButton("−")
        self.intensity_lbl = QLabel("100%")
        self.btn_plus = QPushButton("+")
        self.intensity_lbl.setObjectName("intensityVal")
        self.intensity_lbl.setFixedWidth(36)
        self.intensity_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for btn in [self.btn_minus, self.btn_plus]:
            btn.setFixedSize(34, 30)
            btn.setObjectName("connectBtn")

        self.btn_minus.clicked.connect(lambda: self._on_intensity(-1))
        self.btn_plus.clicked.connect(lambda: self._on_intensity(+1))

        lay.addWidget(self.btn_prev)
        lay.addWidget(self.btn_play)
        lay.addWidget(self.btn_next)
        lay.addWidget(self.btn_stop)
        lay.addWidget(self.timer_lbl)
        lay.addWidget(self.progress_bar, stretch=1)
        lay.addWidget(self.total_lbl)
        lay.addWidget(self.btn_minus)
        lay.addWidget(self.intensity_lbl)
        lay.addWidget(self.btn_plus)

        return bar

    # ------------------------------------------------------------------ Chart

    def _setup_chart(self):
        pass

    def _reset_chart(self):
        self.chart_widget.reset()

    def _update_chart(self, power: int, hr: int):
        self.chart_widget.add_point(power, hr)

    # ------------------------------------------------------------------ Timer

    def _setup_timer(self):
        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        self._playing = False
        self._last_sent_target = None  # prati zadnji poslani target da ne šaljemo duplikate

    def _on_tick(self):
        if self._trainer and self._trainer.state == ConnectionState.CONNECTED:
            if self.player.is_active:
                # dodaj točku PRIJE tick-a da elapsed odgovara poziciji točke
                power = self._trainer._raw_power if self._trainer else 0
                hr = self._hr_monitor.current_hr if self._hr_monitor and self._hr_monitor.connected else 0
                self.chart_widget.add_point(power, hr)

                # Uzmi remaining PRIJE tick-a — za interpolaciju
                remaining_before = self.player.interval_remaining

                was_active = self.player.is_active
                self.player.tick()
                self._update_timebar()

                # Remaining NAKON tick-a — za beep i interpolaciju
                remaining_after = self.player.interval_remaining

                # Evaluiraj prethodni interval i postavi cadence range za novi
                if hasattr(self, "_prev_interval_idx") and self._prev_interval_idx != self.player.current_idx:
                    from ble.trainer import ConnectionState as _CS
                    if self._trainer and self._trainer.state == _CS.CONNECTED:
                        self._last_interval_avg_power = getattr(self._trainer, "_interval_avg_power", 0)
                    self._last_interval_elapsed = getattr(self, "_interval_elapsed", 0)
                    self._evaluate_interval(self._prev_interval_idx)
                    self._interval_elapsed = 0
                    self._play_sound("new_interval")
                    self._cadence_interpolating = False
                    # Postavi cadence range za novi interval
                    self._set_cadence_for_current_interval()
                else:
                    self._interval_elapsed = getattr(self, "_interval_elapsed", 0) + 1
                    # Beep na točno 10 sec — koristimo remaining_after (isti kao na ekranu)
                    if remaining_after == 10:
                        self._play_sound("countdown")

                # Interpolacija cadence ranga — koristimo remaining_after
                if remaining_after <= 10:
                    self._interpolate_cadence_range(remaining_after)

                self._prev_interval_idx = self.player.current_idx

                # Workout završen — evaluiraj zadnji interval pa stop
                if was_active and not self.player.is_active:
                    n = len(self.player.workout.intervals) if self.player.workout else 0
                    print(f"[eval_last] prev_idx={self._prev_interval_idx} n_intervals={n} "
                          f"_interval_elapsed={getattr(self,'_interval_elapsed',0)} "
                          f"_last_interval_elapsed={getattr(self,'_last_interval_elapsed',0)}")
                    from ble.trainer import ConnectionState as _CS
                    if self._trainer and self._trainer.state == _CS.CONNECTED:
                        self._last_interval_avg_power = getattr(self._trainer, "_interval_avg_power", 0)
                    self._last_interval_elapsed = getattr(self, "_interval_elapsed", 0)
                    self._evaluate_interval(self._prev_interval_idx, force=True)
                    self._last_interval_evaluated = True
                    QTimer.singleShot(100, self._on_stop)
                    return

                # pošalji naredbu trenažeru kad se interval promijeni ili na početku
                if self.player.workout:
                    if self.player.is_slope_step:
                        # slope korak — šalji set_grade
                        new_slope = self.player.target_slope
                        if new_slope != self._last_sent_target:
                            self._last_sent_target = new_slope
                            run_async(self._trainer.set_grade(new_slope))
                    else:
                        # ERG korak — šalji set_target_power
                        new_target = self.player.target_power
                        if new_target != self._last_sent_target:
                            self._last_sent_target = new_target
                            run_async(self._trainer.set_target_power(new_target))
                            self._trainer._target_power = new_target
            return

        # Bez spojenog trenažera — samo tik timer za workout player
        if self.player.is_active:
            self.player.tick()
        self._update_timebar()

    def _update_metrics(self, m: MetricsData):
        self.mc_avg_pw.set_value(m.interval_avg_power if m.interval_avg_power > 0 else "—")
        if m.interval_avg_power > 0:
            self._last_interval_avg_power = m.interval_avg_power
        self.mc_avg_hr.set_value(m.interval_avg_hr if m.interval_avg_hr > 0 else "—")
        self.mc_target.set_value(m.target_power if m.target_power > 0 else "—")
        self._update_chart(m.power_3s or m.power, m.heart_rate)
        # ažuriraj time-in-zones i boje zona
        pwr = m.power_3s or m.power
        hr  = m.heart_rate
        # Gauge update — svaki tick
        self.power_gauge.set_value(pwr)
        self.cadence_gauge.set_value(m.cadence if m.cadence > 0 else 0)
        self.hr_gauge.set_value(hr)
        if self.player.is_active:
            if pwr > 0:
                self.power_zone_bar.update_current(pwr)
            if hr > 0:
                self.hr_zone_bar.update_current(hr)
        # osvježi boje kućica svakih 3 sekunde (uvijek, ne samo za aktivni trening)
        self._zone_color_tick += 1
        if self._zone_color_tick >= 3:
            self._zone_color_tick = 0
            self._apply_zone_colors(pwr, hr)
        # slope panel svaki tick — mora reagirati odmah
        self._update_slope_panel()
        # grade widget — vidljiv samo ako workout ima slope intervale
        iv = self.player.current_interval
        has_workout = self.player.workout is not None
        has_slope_wkt = has_workout and any(
            getattr(i, 'slope', None) is not None for i in self.player.workout.intervals)
        is_slope_iv = iv is not None and getattr(iv, 'slope', None) is not None
        self._grade_frame.setVisible(has_slope_wkt)
        if is_slope_iv:
            self.grade_widget.setEnabled(True)
            self.grade_widget.set_base_grade(iv.slope, self.player.current_idx)
        else:
            self.grade_widget.set_base_grade(0.0, -1)
            self.grade_widget.setEnabled(False)

    def _update_timebar(self):
        from datetime import datetime
        elapsed = self.player.elapsed if self.player.workout else getattr(self, '_elapsed', 0)
        if not self.player.workout:
            if self._playing:
                self._elapsed = getattr(self, '_elapsed', 0) + 1
            elapsed = getattr(self, '_elapsed', 0)

        self.tc_total.set_value(self._fmt(elapsed))
        self.tc_clock.set_value(datetime.now().strftime("%H:%M"))

        if self.player.workout:
            self.tc_int_elapsed.set_value(self._fmt(self.player._interval_elapsed))
            self.tc_intrem.set_value(self._fmt(self.player.interval_remaining))
            self.tc_rem.set_value(self._fmt(self.player.total_remaining))
            self.lbl_cur_int.setText(f"Interval: {self.player.interval_label}")
            self.interval_bar.set_current(self.player.current_idx)

            # okomita crta napretka unutar intervala
            iv = self.player.current_interval
            if iv and iv.duration > 0:
                progress = self.player._interval_elapsed / iv.duration
                self.interval_bar.set_progress(min(1.0, progress))
                # sinkroniziraj X poziciju grafa s crticom dolje
                self.chart_widget.set_bar_x_fraction(self.interval_bar.progress_x_fraction)

            self._update_cur_int_ui()

            # transport progress bar
            self.timer_lbl.setText(self._fmt(self.player.elapsed))
            total = self.player.workout.total_duration
            if total > 0:
                w = int(self.progress_bar.width() * self.player.progress)
                self.progress_fill.setFixedWidth(w)
        else:
            self.timer_lbl.setText(self._fmt(getattr(self, '_elapsed', 0)))

    def _update_cur_int_ui(self):
        if self.player.workout:
            self.interval_dots.set_current(self.player.current_idx)
        iv = self.player.current_interval
        if not iv:
            return
        # cur_int_name_lbl uklonjen
        self.cur_int_center_lbl.setText(iv.name)
        ftp = self.player.workout.ftp
        intensity = self.player.intensity_pct
        if iv.slope is not None:
            if self.mode != TrainerMode.SIMULATION:
                self._set_mode(TrainerMode.SIMULATION)
            ref_watts = round(iv.power_pct * ftp * intensity / 100)
            self.workout_type_badge.setText("SLOPE")
            self.workout_type_badge.setStyleSheet("background:#1a3a2a;color:#4ecb8d;border:1px solid #2a6a4a;font-size:10px;padding:2px 6px;border-radius:4px;")
            detail     = f"⛰ {iv.slope:+.1f}%  ·  ref {ref_watts} W  ·  {self._fmt(iv.duration)}"
            self.mc_target.lbl.setText("REF. SNAGA")
            self.mc_target.set_unit("W")
            self.mc_target.set_value(ref_watts if ref_watts > 0 else "—")
        elif iv.type in ("ramp", "warmup", "cooldown"):
            if self.mode != TrainerMode.ERG:
                self._set_mode(TrainerMode.ERG)
            w_start = round(iv.power_pct     * ftp * intensity / 100)
            w_end   = round(iv.power_pct_end * ftp * intensity / 100)
            label   = {"ramp": "RAMP", "warmup": "WARMUP", "cooldown": "COOLDOWN"}[iv.type]
            self.workout_type_badge.setText(label)
            self.workout_type_badge.setStyleSheet("background:#C0DD97;color:#27500A;font-size:10px;padding:2px 6px;border-radius:4px;")
            detail = f"{round(iv.power_pct*100)}→{round(iv.power_pct_end*100)}% FTP  ·  {w_start}→{w_end} W  ·  {self._fmt(iv.duration)}"
            self.mc_target.lbl.setText("ZADANA SNAGA")
            self.mc_target.set_unit("W")
            self.mc_target.set_value(self.player.target_power or "—")
        else:
            if self.mode != TrainerMode.ERG:
                self._set_mode(TrainerMode.ERG)
            tw = self.player.target_power
            self.workout_type_badge.setText("ERG")
            self.workout_type_badge.setStyleSheet("background:#C0DD97;color:#27500A;font-size:10px;padding:2px 6px;border-radius:4px;")
            detail = f"{round(iv.power_pct*100)}% FTP  ·  {tw} W  ·  {self._fmt(iv.duration)}"
            self.mc_target.lbl.setText("ZADANA SNAGA")
            self.mc_target.set_unit("W")
            self.mc_target.set_value(tw if tw > 0 else "—")
        # cur_int_detail_lbl uklonjen
        self.cur_int_detail_center_lbl.setText(detail)

    # ------------------------------------------------------------------ intervals.icu

    def _on_intervals_connect(self):
        from intervals.settings_dialog import IntervalsSettingsDialog
        from intervals.client import load_local_athlete, save_config, save_local_athlete
        local = load_local_athlete()
        dlg = IntervalsSettingsDialog(
            self,
            athlete_id=self._intervals_athlete_id,
            api_key=self._intervals_api_key,
            tolerance=self._tolerance,
            local_ftp=local.get("ftp", 0),
            local_hr_max=local.get("hr_max", 0),
            local_power_zones=local.get("power_zones", []),
            local_hr_zones=local.get("hr_zones", []),
            cadence_tolerance=local.get("cadence_tolerance", 5),
        )
        if dlg.exec():
            aid, key = dlg.get_credentials()
            self._intervals_athlete_id = aid
            self._intervals_api_key    = key
            self._tolerance            = dlg.tolerance
            save_config(aid, key)
            # Spremi zone i kadence postavke lokalno
            if dlg.local_ftp > 0 or dlg.local_hr_max > 0 or dlg.local_power_zones:
                new_ftp    = dlg.local_ftp    or local.get("ftp", 0)
                new_hr_max = dlg.local_hr_max or local.get("hr_max", 0)
                dlg_pw = getattr(dlg, "local_power_zones", [])
                dlg_hr = getattr(dlg, "local_hr_zones", [])
                new_power_zones = (dlg_pw if any(z.get("max_val", 0) > 0 for z in dlg_pw)
                                   else self._build_power_zones_from_ftp(new_ftp) if new_ftp > 0
                                   else local.get("power_zones", []))
                new_hr_zones = (dlg_hr if any(z.get("max_val", 0) > 0 for z in dlg_hr)
                                else self._build_hr_zones_from_max(new_hr_max) if new_hr_max > 0
                                else local.get("hr_zones", []))
                save_local_athlete(
                    ftp=new_ftp,
                    hr_max=new_hr_max,
                    power_zones=new_power_zones,
                    hr_zones=new_hr_zones,
                    cadence_tolerance=dlg.cadence_tolerance,
                )
                # Invalidate cache
                if hasattr(self, '_local_athlete_cache'):
                    del self._local_athlete_cache
                self._apply_local_athlete({
                    "ftp": new_ftp, "hr_max": new_hr_max,
                    "power_zones": new_power_zones, "hr_zones": new_hr_zones,
                    "cadence_tolerance": dlg.cadence_tolerance,
                })
            self.topbar_athlete_lbl.setText("⏳ Spajanje...")
            self._intervals_fetch_start()

    def _on_intervals_today(self):
        if not self._intervals_workouts_today:
            self._intervals_fetch_start()
            return
        self._show_today_workout_dialog()

    def _show_today_workout_dialog(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        workouts = self._intervals_workouts_today
        if not workouts:
            return
        # prikazujemo samo prvi trening
        w = workouts[0]
        name = w.get("name") or w.get("workout_name") or "Trening za danas"
        duration = w.get("moving_time") or w.get("workout_doc", {}).get("duration", 0)
        mins = f"{duration // 60} min" if duration else ""
        desc = w.get("description") or ""

        from PyQt6.QtWidgets import QScrollArea, QFrame, QHBoxLayout as _QHBoxLayout
        QHBoxLayout = _QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Trening za danas")
        dlg.setMinimumWidth(400)
        dlg.setMinimumHeight(300)
        dlg.setMaximumHeight(600)
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 8)
        outer.setSpacing(0)

        # Scroll area za opis
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner_w = QWidget()
        lay = QVBoxLayout(inner_w)
        lay.setContentsMargins(16, 16, 16, 8)
        lay.setSpacing(10)
        scroll.setWidget(inner_w)
        outer.addWidget(scroll, stretch=1)

        title_lbl = QLabel(f"📅  {name}")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        title_lbl.setWordWrap(True)
        lay.addWidget(title_lbl)

        if mins:
            lay.addWidget(QLabel(f"Trajanje: {mins}"))
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("font-size: 11px; color: #888;")
            desc_lbl.setWordWrap(True)
            lay.addWidget(desc_lbl)
        lay.addStretch()

        workout_doc = w.get("workout_doc")
        # Proslijedi name i ftp u workout_doc
        if workout_doc:
            if not workout_doc.get("name"):
                workout_doc["name"] = name
            if not workout_doc.get("ftp"):
                ftp_val = w.get("icu_ftp") or w.get("ftp")
                if ftp_val:
                    workout_doc["ftp"] = ftp_val
        description = w.get("description", "")
        ftp_val = (workout_doc or {}).get("ftp") or w.get("icu_ftp") or self._intervals_ftp()
        has_workout = isinstance(workout_doc, dict) or bool(description)
        load_btn = QPushButton("▶  Učitaj trening")
        load_btn.setStyleSheet("padding: 5px 10px; font-weight: 600;")
        load_btn.setFixedHeight(30)
        load_btn.setEnabled(has_workout)
        _doc  = dict(workout_doc) if isinstance(workout_doc, dict) else None
        _desc = description
        _name = name
        _ftp  = ftp_val
        def _load(doc=_doc, desc=_desc, wname=_name, ftp=_ftp, d=dlg):
            try:
                from workout.parser import IntervalsParser, DescriptionParser
                # Pokušaj s description parserom ako postoji — on čuva slope tagove
                if desc and desc.strip():
                    workout = DescriptionParser().parse(desc, ftp=int(ftp or 220), name=wname)
                    if workout.intervals:
                        self._load_workout(workout)
                        d.accept()
                        return
                # Fallback: workout_doc JSON
                if doc:
                    doc["name"] = wname
                    if not doc.get("ftp") and ftp:
                        doc["ftp"] = int(ftp)
                    workout = IntervalsParser().parse_dict(doc)
                    self._load_workout(workout)
            except Exception as e:
                import traceback
                print(f"[_load] GREŠKA: {e}")
                traceback.print_exc()
            d.accept()
        load_btn.clicked.connect(_load)

        edit_btn = QPushButton("✏  Ažuriraj")
        edit_btn.setFixedHeight(30)
        edit_btn.setEnabled(bool(description))

        def _edit(_checked=False, desc=_desc, wname=_name, d=dlg):
            d.accept()
            QTimer.singleShot(100, lambda: self._on_enter_workout(
                prefill_text=desc, prefill_name=wname))

        edit_btn.clicked.connect(_edit)

        cancel = QPushButton("Zatvori")
        cancel.setFixedHeight(30)
        cancel.clicked.connect(dlg.reject)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 0, 16, 0)
        btn_row.addWidget(cancel)
        btn_row.addStretch()
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(load_btn)
        outer.addLayout(btn_row)
        dlg.exec()

    def _intervals_fetch_start(self):
        """Pokreni dohvat podataka u zasebnom threadu."""
        from intervals.client import fetch_all
        fetch_all(
            self._intervals_athlete_id,
            self._intervals_api_key,
            on_done=lambda d, w: self._intervals_done_signal.emit(d, w),
            on_error=lambda e: self._intervals_error_signal.emit(e),
        )

    def _set_cadence_for_current_interval(self):
        """Postavi cadence range za trenutni interval."""
        iv = self.player.current_interval
        if iv is None:
            return
        local = self._get_local_athlete_cached()
        tol = local.get("cadence_tolerance", 5)
        rpm = iv.cadence_rpm if iv.cadence_rpm > 0 else self._cadence_for_interval(iv)
        if rpm > 0:
            self.cadence_gauge.set_cadence_rpm(rpm, "", tol)


    def _interpolate_cadence_range(self, remaining: int):
        """Linearno interpoliraj cadence range prema sljedećem intervalu (zadnjih 10s)."""
        if not self.player.workout:
            return
        intervals = self.player.workout.intervals
        cur_idx  = self.player.current_idx
        next_idx = cur_idx + 1
        if next_idx >= len(intervals):
            return  # zadnji interval

        local = self._get_local_athlete_cached()
        tol = local.get("cadence_tolerance", 5)

        cur_iv  = intervals[cur_idx]
        next_iv = intervals[next_idx]

        cur_rpm  = cur_iv.cadence_rpm  if cur_iv.cadence_rpm  > 0 else self._cadence_for_interval(cur_iv)
        next_rpm = next_iv.cadence_rpm if next_iv.cadence_rpm > 0 else self._cadence_for_interval(next_iv)

        if cur_rpm <= 0 or next_rpm <= 0 or cur_rpm == next_rpm:
            return

        # remaining: 10 → alpha=0.0, 1 → alpha=0.9, 0 → alpha=1.0
        alpha = (10 - remaining) / 10.0
        alpha = max(0.0, min(1.0, alpha))
        interp_rpm = cur_rpm + alpha * (next_rpm - cur_rpm)

        self._cadence_interpolating = True
        self.cadence_gauge.set_cadence_range_direct(interp_rpm - tol, interp_rpm + tol)

    def _play_sound(self, kind: str):
        """
        Reproduciraj zvučni signal u zasebnom threadu da ne blokira UI.
        kind: 'new_interval' — dva kratka beep-a (novi interval počeo)
              'countdown'    — jedan kratki beep (10 sec do kraja)
        """
        import threading
        def _beep():
            try:
                import winsound
                if kind == "new_interval":
                    winsound.Beep(880, 120)
                    import time; time.sleep(0.08)
                    winsound.Beep(1100, 120)
                else:  # countdown
                    winsound.Beep(660, 150)
            except Exception:
                try:
                    from PyQt6.QtWidgets import QApplication
                    QApplication.beep()
                except Exception:
                    pass
        threading.Thread(target=_beep, daemon=True).start()

    def _get_local_athlete_cached(self) -> dict:
        """Vrati lokalne athlete podatke — cache da ne čitamo disk svaki tick."""
        if not hasattr(self, '_local_athlete_cache'):
            from intervals.client import load_local_athlete
            self._local_athlete_cache = load_local_athlete()
        return self._local_athlete_cache

    def _cadence_for_interval(self, iv) -> int:
        """Vrati preporučenu kadencu za interval na osnovu power zone."""
        if not self.player.workout:
            return 0
        ftp = self.player.workout.ftp or 240
        watts = round(iv.power_pct * ftp)  # round da izbjegnemo float precision (0.55*220=121.000...01)
        local = self._get_local_athlete_cached()
        power_zones = local.get("power_zones", [])
        default_cadence = [75, 85, 88, 90, 95, 100, 105]
        for i, z in enumerate(power_zones):
            if z.get("min_val", 0) <= watts <= z.get("max_val", 9999):
                rpm = z.get("cadence_rpm", 0)
                if rpm <= 0:
                    rpm = default_cadence[i] if i < len(default_cadence) else 85
                return rpm
        return 0

    def _build_power_zones_from_ftp(self, ftp: int) -> list[dict]:
        """Izračunaj 7 power zona iz FTP — standardni Coggan % granice."""
        pcts   = [55, 75, 90, 105, 120, 150]
        names  = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
        colors = ["#009e80","#009e00","#ffcb0e","#ff7f0e","#dd0447","#6633cc","#504861"]
        zones = []
        prev = 0
        for i, pct in enumerate(pcts):
            max_w = round(ftp * pct / 100)
            zones.append({"name": names[i], "color": colors[i],
                          "min_val": int(prev + 1 if prev > 0 else 1), "max_val": int(max_w)})
            prev = max_w
        zones.append({"name": "Z7", "color": colors[6],
                      "min_val": prev + 1, "max_val": 600})
        return zones

    def _build_hr_zones_from_max(self, hr_max: int) -> list[dict]:
        """Izračunaj 7 HR zona iz HR max — standardni % granice."""
        pcts   = [60, 70, 80, 87, 93, 97, 100]
        names  = ["Z1","Z2","Z3","Z4","Z5","Z6","Z7"]
        colors = ["#009e80","#009e00","#ffcb0e","#ff7f0e","#dd0447","#6633cc","#504861"]
        zones = []
        prev = 0
        for i, pct in enumerate(pcts):
            max_bpm = round(hr_max * pct / 100)
            zones.append({"name": names[i], "color": colors[i],
                          "min_val": prev + 1 if prev > 0 else 1, "max_val": max_bpm})
            prev = max_bpm
        return zones

    def _apply_local_athlete(self, local: dict):
        """Primijeni lokalno spremljene FTP i HR zone na UI — koristi se kao fallback."""
        ftp = local.get("ftp")
        power_zones = local.get("power_zones", [])
        hr_zones = local.get("hr_zones", [])
        hr_max = local.get("hr_max")

        stats_parts = []
        if ftp:
            stats_parts.append(f"FTP: {ftp} W")
            if self.player.workout:
                self.player.workout.ftp = int(ftp)
        if hr_max:
            stats_parts.append(f"HR max: {hr_max}")
        stats = "  ·  ".join(stats_parts)

        if stats_parts:
            self.topbar_athlete_lbl.setText(f"👤 Lokalni profil  {stats}")

        if power_zones:
            td = self.player.workout.total_duration if self.player.workout else 0
            self.power_zone_bar.set_zones(power_zones, td)
            self.power_gauge.set_zones(power_zones, ftp=ftp or 240)
        if hr_zones:
            td = self.player.workout.total_duration if self.player.workout else 0
            self.hr_zone_bar.set_zones(hr_zones, td)
            self.hr_gauge.set_zones(hr_zones)

    def _intervals_on_done(self, data: dict, workouts: list):
        """Callback — prima se u Qt threadu kroz signal."""
        name = data.get("name") or "—"
        ftp  = data.get("ftp")
        weight = data.get("weight")
        lthr = data.get("lthr")
        stats_parts = []
        if ftp:    stats_parts.append(f"FTP: {ftp} W")
        if weight: stats_parts.append(f"{weight} kg")
        if lthr:   stats_parts.append(f"LTHR: {lthr}")
        stats = "  ·  ".join(stats_parts)
        if ftp and isinstance(ftp, (int, float)) and self.player.workout:
            self.player.workout.ftp = int(ftp)
        ss_raw = data.get("sportSettings") or []
        if isinstance(ss_raw, list):
            sport_settings = next(
                (s for s in ss_raw if "Ride" in s.get("types", [])),
                ss_raw[0] if ss_raw else {}
            )
        else:
            sport_settings = ss_raw
        if not ftp:
            ftp = sport_settings.get("ftp") or sport_settings.get("indoor_ftp")
            if ftp:
                stats_parts.append(f"FTP: {ftp} W")
                stats = "  ·  ".join(stats_parts)
        power_zones = self._parse_power_zones(sport_settings, ftp)
        hr_zones    = self._parse_hr_zones(sport_settings)
        self._intervals_workouts_today = workouts
        self._update_athlete_ui(name, stats, power_zones, hr_zones)
        self._update_today_ui(workouts)

        # Spremi lokalno kao fallback za sljedeće pokretanje bez interneta
        if ftp or power_zones or hr_zones:
            from intervals.client import save_local_athlete
            hr_max_val = hr_zones[-1]["max_val"] if hr_zones else int(data.get("hr_max") or 0)
            local_existing = self._get_local_athlete_cached()
            # Zadrži cadence_rpm iz lokalno spremljenih zona — intervals.icu ih ne poznaje
            existing_pw = {z.get("name"): z.get("cadence_rpm", 0)
                           for z in local_existing.get("power_zones", [])}
            for z in power_zones:
                if z.get("name") in existing_pw and existing_pw[z["name"]] > 0:
                    z["cadence_rpm"] = existing_pw[z["name"]]
            save_local_athlete(
                ftp=int(ftp) if ftp else 0,
                hr_max=hr_max_val,
                power_zones=power_zones,
                hr_zones=hr_zones,
                cadence_tolerance=local_existing.get("cadence_tolerance", 5),
            )
            # Invalidate cache
            if hasattr(self, '_local_athlete_cache'):
                del self._local_athlete_cache

    def _intervals_on_error(self, err: str):
        """Callback — prima se u Qt threadu kroz signal."""
        logger.error(f"intervals.icu greška: {err}")
        # Učitaj lokalne podatke i primijeni ih — ne brišemo zone zbog greške spajanja
        from intervals.client import load_local_athlete
        local = load_local_athlete()
        if local:
            self._apply_local_athlete(local)
            self.topbar_athlete_lbl.setText(
                f"⚠ intervals.icu nedostupan  —  {self.topbar_athlete_lbl.text().replace('👤 ', '')}"
                if "Lokalni" not in self.topbar_athlete_lbl.text()
                else self.topbar_athlete_lbl.text().replace("👤", "⚠")
            )
        else:
            self._update_athlete_ui("⚠ Greška spajanja", err[:60], [], [])


    def _parse_power_zones(self, settings: dict, ftp) -> list[dict]:
        """Parsira power zone granice iz sportSettings."""
        zone_pcts  = settings.get("power_zones", [55, 75, 90, 105, 120, 150])
        zone_names = settings.get("power_zone_names",
                     ["Z1","Z2","Z3","Z4","Z5","Z6","Z7"])
        colors = ["#009e80","#009e00","#ffcb0e","#ff7f0e","#dd0447","#6633cc","#504861"]
        ftp_val = int(ftp) if ftp else 240
        zones = []
        prev = 0
        for i, pct in enumerate(zone_pcts):
            min_w = prev + 1 if prev > 0 else 1
            max_w = round(ftp_val * pct / 100)
            label = zone_names[i] if i < len(zone_names) else f"Z{i+1}"
            # skrati naziv na Z1-Z7 za prikaz
            short = f"Z{i+1}"
            zones.append({"name": short, "color": colors[i % len(colors)],
                          "min_val": int(min_w), "max_val": int(max_w)})
            prev = max_w
        # Uvijek dodaj Z7 — intervals.icu ga ne vraća eksplicitno
        zones.append({"name": "Z7", "color": "#504861",
                      "min_val": prev + 1, "max_val": 600})
        return zones  # već je točno 7

    def _parse_hr_zones(self, settings: dict) -> list[dict]:
        """Parsira HR zone granice iz sportSettings."""
        hr_thresholds = settings.get("hr_zones", [])
        zone_names    = settings.get("hr_zone_names",
                        ["Z1","Z2","Z3","Z4","Z5","Z6","Z7"])
        colors = ["#009e80","#009e00","#ffcb0e","#ff7f0e","#dd0447","#6633cc","#504861"]
        if not hr_thresholds:
            return []
        zones = []
        prev = 0
        for i, max_bpm in enumerate(hr_thresholds):
            min_bpm = prev + 1 if prev > 0 else 1
            short = f"Z{i+1}"
            zones.append({"name": short, "color": colors[i % len(colors)],
                          "min_val": min_bpm, "max_val": max_bpm})
            prev = max_bpm
        return zones


    def _update_athlete_ui(self, name: str, stats: str,
                            power_zones: list = None, hr_zones: list = None):
        # Athlete info ide u topbar
        self.topbar_athlete_lbl.setText(f"👤 {name}  {stats}")
        self.intervals_connect_btn.setText("Postavke ↗")
        self.intervals_today_btn.setVisible(True)
        if power_zones:
            td = self.player.workout.total_duration if self.player.workout else 0
            self.power_zone_bar.set_zones(power_zones, td)
            self.power_gauge.set_zones(power_zones, ftp=self._intervals_ftp())
        if hr_zones:
            td = self.player.workout.total_duration if self.player.workout else 0
            self.hr_zone_bar.set_zones(hr_zones, td)
            self.hr_gauge.set_zones(hr_zones)

    def _update_today_ui(self, workouts: list):
        if workouts:
            self.topbar_today_lbl.setText("")
            self.intervals_today_btn.setText(f"Danas ({len(workouts)})")
            self.intervals_today_btn.setEnabled(True)
            self.intervals_today_btn.setStyleSheet(
                "font-size: 11px; border: 1px solid #c8a84b; color: #c8a84b;")
        else:
            self.topbar_today_lbl.setText("")
            self.intervals_today_btn.setText("Danas")
            self.intervals_today_btn.setEnabled(False)
            self.intervals_today_btn.setStyleSheet("font-size: 11px;")

    # ------------------------------------------------------------------ Helpers

    def _fmt(self, s: int) -> str:
        s = max(0, int(s))
        return f"{s//60:02d}:{s%60:02d}"

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setObjectName("sectionLabel")
        return lbl

    def _device_row(self, name: str, status: str, warning: bool) -> QFrame:
        row = QFrame()
        row.setObjectName("deviceRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(7, 4, 7, 4)
        name_lbl = QLabel(name)
        status_lbl = QLabel(status)
        status_lbl.setObjectName("badgeWarning" if warning else "badgeNeutral")
        lay.addWidget(name_lbl)
        lay.addStretch()
        lay.addWidget(status_lbl)
        return row

    # ------------------------------------------------------------------ Slots

    def _evaluate_interval(self, idx: int, force: bool = False):
        """Evaluiraj odrađeni interval i postavi boju lampice.
        force=True preskače min_time provjeru (za zadnji interval workota)."""
        if not self.player.workout:
            print(f"[eval] idx={idx} SKIP: no workout")
            return
        ivs = self.player.workout.intervals
        if idx < 0 or idx >= len(ivs):
            print(f"[eval] idx={idx} SKIP: out of range (len={len(ivs)})")
            return
        iv = ivs[idx]
        ftp = self.player.workout.ftp

        if not force:
            elapsed_in_interval = self.player._interval_elapsed if self.player.workout else 0
            elapsed_in_interval = getattr(self, "_last_interval_elapsed", elapsed_in_interval)
            min_time = max(30, int(iv.duration * 0.50))
            if elapsed_in_interval < min_time:
                print(f"[eval] idx={idx} SKIP: elapsed={elapsed_in_interval} < min={min_time}")
                return

        target_pct = (iv.power_pct + iv.power_pct_end) / 2 if iv.type in ("ramp", "warmup", "cooldown") else iv.power_pct
        target_w = target_pct * ftp * self.player.intensity_pct / 100
        avg_w = getattr(self, "_last_interval_avg_power", 0)
        print(f"[eval] idx={idx} '{iv.name}' force={force} target_w={target_w:.0f} avg_w={avg_w:.0f}")

        if target_w <= 0 or avg_w <= 0:
            self.interval_dots.set_result(idx, 1)
            return

        diff_pct = (avg_w - target_w) / target_w * 100
        if diff_pct >= 5:
            result = 2
        elif diff_pct >= -5:
            result = 1
        else:
            result = 3
        print(f"[eval] idx={idx} diff={diff_pct:.1f}% → result={result}")
        self.interval_dots.set_result(idx, result)

    def _on_blink_tick(self):
        """Blink tick za slope lampice — 500ms."""
        self.power_gauge.blink_tick()

    def _update_slope_panel(self):
        iv = self.player.current_interval
        pwr = self.power_gauge._value

        # Kadenca zona — lookup po power zoni intervala
        # Preskačemo ako je aktivna interpolacija (zadnjih 10s intervala)
        if iv is not None and not getattr(self, '_cadence_interpolating', False):
            local = self._get_local_athlete_cached()
            tol = local.get("cadence_tolerance", 5)
            rpm = getattr(iv, 'cadence_rpm', 0)
            if rpm > 0:
                self.cadence_gauge.set_cadence_rpm(rpm, "", tol)
            else:
                cad_rpm = self._cadence_for_interval(iv)
                if cad_rpm > 0:
                    self.cadence_gauge.set_cadence_rpm(cad_rpm, "", tol)

        # Lampice — samo u slope modu s referencom
        is_slope = iv is not None and getattr(iv, "slope", None) is not None
        ref = round(iv.power_pct * self._intervals_ftp()) if (is_slope and iv and iv.power_pct > 0) else None
        active = is_slope and ref is not None and self.player.is_active
        if active and pwr > 0:
            tol = getattr(self, "_tolerance", 15)
            lamp_low  = pwr < ref - tol   # treba pojačati — crvena desno
            lamp_high = pwr > ref + tol   # treba smanjiti  — plava lijevo
            self.power_gauge.set_lamps(lamp_low, lamp_high, active=True)
        else:
            self.power_gauge.set_lamps(False, False, active=active)

    def _set_playing_ui(self, playing: bool):
        has_workout = self.player.workout is not None
        always_block = [
            self.intervals_connect_btn,
            self.intervals_today_btn,
            self.load_btn,
            self.enter_btn,
        ]
        workout_block = [
            self.unload_btn,
            self.unload_btn2,
            self.btn_erg,
            self.btn_sim,
        ]
        for btn in always_block:
            btn.setEnabled(not playing)
        if has_workout:
            for btn in workout_block:
                btn.setEnabled(not playing)
        # Spajanje uređaja — blokirano dok traje trening
        self.trainer_dev_row.setEnabled(not playing)
        self.hr_dev_row.setEnabled(not playing)

    def _on_play_pause(self):
        # Blokiraj play ako trenažer nije spojen
        if not self._playing:
            from ble.trainer import ConnectionState
            if not self._trainer or self._trainer.state != ConnectionState.CONNECTED:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Trenažer nije spojen",
                                    "Spoji trenažer prije pokretanja treninga.")
                return
        self._playing = not self._playing
        if self._playing:
            self.btn_play.setText("⏸")
            self.player.is_active = True
            self._timer.start()
            if self.player.elapsed == 0:
                self._reset_chart()
            self._set_playing_ui(True)

        else:
            self.btn_play.setText("▶")
            self.player.is_active = False
            self._timer.stop()
            self._set_playing_ui(False)

    def _on_stop(self):
        self._playing = False
        self.btn_play.setText("▶")
        self.player.is_active = False
        self._timer.stop()
        self._set_playing_ui(False)
        # Evaluiraj zadnji interval samo ako nije već evaluiran u tick bloku
        if (self.player.workout and self._prev_interval_idx >= 0
                and not getattr(self, '_last_interval_evaluated', False)):
            from ble.trainer import ConnectionState as _CS
            if self._trainer and self._trainer.state == _CS.CONNECTED:
                self._last_interval_avg_power = getattr(self._trainer, "_interval_avg_power", 0)
            self._last_interval_elapsed = getattr(self, "_interval_elapsed", 0)
            self._evaluate_interval(self._prev_interval_idx, force=True)
        self._last_interval_evaluated = False

        self.player.reset()
        self._elapsed = 0
        self._reset_chart()
        self.timer_lbl.setText("00:00")
        self.progress_fill.setFixedWidth(0)
        self.interval_bar.set_current(0)
        self.interval_bar.set_progress(0.0)
        # Sigurnosno pošalji slope 0% samo u slope modu — u ERG modu ne diramo ništa
        if self._trainer and self._trainer.state == ConnectionState.CONNECTED:
            if self.mode == TrainerMode.SIMULATION:
                run_async(self._trainer.set_grade(0.0))

    def _on_prev(self):
        self.player.prev_interval()
        self._last_sent_target = None
        self._reset_interval_stats()
        self.interval_bar.set_current(self.player.current_idx)
        self.chart_widget.seek(self.player.elapsed)

    def _on_next(self):
        self.player.next_interval()
        self._last_sent_target = None
        self._reset_interval_stats()
        self.interval_bar.set_current(self.player.current_idx)
        self.chart_widget.seek(self.player.elapsed)

    def _on_intensity(self, delta: int):
        self.player.change_intensity(delta)
        self._last_sent_target = None
        self.intensity_lbl.setText(f"{self.player.intensity_pct}%")

    def _on_interval_clicked(self, idx: int):
        self.player.jump_to_interval(idx)
        self._last_sent_target = None
        self._reset_interval_stats()
        self.interval_bar.set_current(self.player.current_idx)
        self.chart_widget.seek(self.player.elapsed)

    def _reset_interval_stats(self):
        """Resetira avg snagu i HR za novi interval."""
        if self._trainer and self._trainer.state == ConnectionState.CONNECTED:
            self._trainer.reset_interval_stats()
        self._int_hr_sum = 0
        self._int_hr_cnt = 0

    def _on_free_slider_moved(self, value: int):
        """Ažurira prikaz dok se slider kreće."""
        if self.mode == TrainerMode.SIMULATION:
            grade = value / 10.0
            self.free_ctrl_val.setText(f"{grade:.1f} %")
            self.mc_target.set_value(f"{grade:.1f}")
            self.mc_target.set_unit("%")
        else:
            self.free_ctrl_val.setText(f"{value} W")
            self.mc_target.set_value(value)
            self.mc_target.set_unit("W")

    def _on_free_slider_released(self):
        value = self.free_slider.value()
        if not self._trainer or self._trainer.state != ConnectionState.CONNECTED:
            return
        if self.mode == TrainerMode.SIMULATION:
            grade = value / 10.0
            run_async(self._trainer.set_grade(grade))
        else:
            run_async(self._trainer.set_target_power(value))

    def _on_grade_widget_changed(self, grade: float):
        """Korisnik je pritisnuo +/- na grade widgetu — pošalji nagib trenažeru."""
        if not self._trainer or self._trainer.state != ConnectionState.CONNECTED:
            return
        run_async(self._trainer.set_grade(grade))

    def _set_mode(self, mode: TrainerMode):
        self.mode = mode
        self.btn_erg.setObjectName("modeActive" if mode == TrainerMode.ERG else "modeInactive")
        self.btn_sim.setObjectName("modeActive" if mode == TrainerMode.SIMULATION else "modeInactive")
        self.btn_erg.style().unpolish(self.btn_erg); self.btn_erg.style().polish(self.btn_erg)
        self.btn_sim.style().unpolish(self.btn_sim); self.btn_sim.style().polish(self.btn_sim)

        if not self.player.workout:
            if mode == TrainerMode.ERG:
                self.free_ctrl_lbl.setText("Ciljna snaga")
                self.free_slider.setRange(50, 500)
                self.free_slider.setValue(100)
                self.free_ctrl_val.setText("100 W")
                self.mc_target.lbl.setText("ZADANA SNAGA")
                self.mc_target.set_unit("W")
                self.mc_target.set_value(100)
                if self._trainer and self._trainer.state == ConnectionState.CONNECTED:
                    run_async(self._trainer.set_target_power(100))
            else:
                self.free_ctrl_lbl.setText("Nagib")
                self.free_slider.setRange(-100, 200)
                self.free_slider.setValue(0)
                self.free_ctrl_val.setText("0.0 %")
                self.mc_target.set_value("—")
                self.mc_target.set_unit("")
                if self._trainer and self._trainer.state == ConnectionState.CONNECTED:
                    run_async(self._trainer.set_grade(0.0))

    def _on_enter_from_btn(self):
        """Tipka Unesi — prepuni editorom ako je workout učitan."""
        w = self.player.workout
        if w and w.description:
            self._on_enter_workout(prefill_text=w.description, prefill_name=w.name)
        else:
            self._on_enter_workout()

    def _on_enter_workout(self, prefill_text: str = "", prefill_name: str = ""):
        """Otvori dijalog s tabovima Upiši / Predlošci."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                      QLabel, QTextEdit, QPushButton,
                                      QTabWidget, QWidget, QScrollArea, QFrame)
        from PyQt6.QtGui import QFont, QTextCursor
        from PyQt6.QtCore import Qt

        dlg = QDialog(self)
        dlg.setWindowTitle("Unesi workout")
        dlg.setMinimumWidth(680)
        dlg.setMinimumHeight(520)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        tabs = QTabWidget()
        lay.addWidget(tabs, stretch=1)

        # ── Tab 1: Upiši ──────────────────────────────────────────
        tab_write = QWidget()
        tw_lay = QHBoxLayout(tab_write)
        tw_lay.setContentsMargins(8, 8, 8, 4)
        tw_lay.setSpacing(8)

        # Lijeva kolona — blokovi
        blocks_w = QWidget()
        blocks_w.setFixedWidth(160)
        bl_lay = QVBoxLayout(blocks_w)
        bl_lay.setContentsMargins(0, 0, 0, 0)
        bl_lay.setSpacing(4)
        bl_title = QLabel("BLOKOVI")
        bl_title.setStyleSheet("font-size: 9px; color: #555; letter-spacing: 1px;")
        bl_lay.addWidget(bl_title)

        editor = QTextEdit()
        editor.setFont(QFont("Courier New", 10))
        editor._template_name = "Workout"

        BLOCKS = [
            ("▲ Zagrijavanje",  "- 15m Ramp 55-75% FTP WarmUp\n"),
            ("▼ Hlađenje",      "- 10m Ramp 70-45% FTP CoolDown\n"),
            ("━ Steady",        "- 10m 80% FTP SteadyState\n"),
            ("↻ Recovery",      "- 5m 55% FTP Recovery\n"),
            ("⛰ Slope",        "- 10m 75% FTP #2.0% SLOPE# Climb\n"),
            ("⚡ Sprint",       "- 30s 150% FTP Sprint\n"),
            ("🔁 Repeat 3x",    "3x\n"),
        ]

        for label, snippet in BLOCKS:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "text-align: left; padding: 5px 8px; font-size: 11px;"
                "border-radius: 4px;"
            )
            def _insert(checked=False, s=snippet):
                cursor = editor.textCursor()
                # Ako je kursor na sredini retka, idi na kraj retka
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                # Dodaj newline ako nismo na početku praznog retka
                pos = cursor.position()
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.KeepAnchor)
                line_text = cursor.selectedText().strip()
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                if line_text:
                    cursor.insertText("\n" + s)
                else:
                    cursor.insertText(s)
                editor.setTextCursor(cursor)
                editor.setFocus()
            btn.clicked.connect(_insert)
            bl_lay.addWidget(btn)

        bl_lay.addStretch()
        tw_lay.addWidget(blocks_w)

        # Desna kolona — editor
        right_w = QWidget()
        r_lay = QVBoxLayout(right_w)
        r_lay.setContentsMargins(0, 0, 0, 0)
        r_lay.setSpacing(4)
        hint = QLabel("Klikni blok da dodaš, ili upiši/zalijepi direktno:")
        hint.setStyleSheet("font-size: 10px; color: #888;")
        r_lay.addWidget(hint)
        r_lay.addWidget(editor, stretch=1)
        error_lbl = QLabel("")
        error_lbl.setStyleSheet("font-size: 11px; color: #dd0447;")
        r_lay.addWidget(error_lbl)
        tw_lay.addWidget(right_w, stretch=1)
        tabs.addTab(tab_write, "Upiši")

        # Predpopuni iz vanjskog poziva (npr. Ažuriraj iz Danas dijaloga)
        if prefill_text:
            editor.setPlainText(prefill_text)
            editor._template_name = prefill_name or "Workout"
            tabs.setCurrentIndex(0)

        # ── Tab 2: Predlošci ──────────────────────────────────────
        tab_tmpl = QWidget()
        tt_lay = QVBoxLayout(tab_tmpl)
        tt_lay.setContentsMargins(4, 4, 4, 4)
        tt_lay.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(4, 4, 4, 4)
        inner_lay.setSpacing(6)
        scroll.setWidget(inner)
        tt_lay.addWidget(scroll)
        tabs.addTab(tab_tmpl, "Predlošci")

        ftp = self._intervals_ftp()

        TEMPLATES = [
            ("Recovery ride", "Lagano oporavak, sve u Z1-Z2",
             "- 10m Ramp 50-60% FTP WarmUp\n- 40m 55% FTP Recovery\n- 10m Ramp 60-45% FTP CoolDown"),
            ("Endurance — slope", "Dugi aerobni blok na nagibu",
             "- 10m Ramp 55-70% FTP WarmUp\n\n3x\n- 20m 70% FTP #2.0% SLOPE# Endurance\n- 5m 55% FTP Recovery\n\n- 10m Ramp 65-45% FTP CoolDown"),
            ("Sweet Spot", "Klasični sweet spot 84-97% FTP",
             "- 15m Ramp 55-75% FTP WarmUp\n\n3x\n- 12m 88% FTP SweetSpot\n- 5m 55% FTP Recovery\n\n- 10m Ramp 70-45% FTP CoolDown"),
            ("Threshold", "Prag izdržljivosti 95-105% FTP",
             "- 15m Ramp 55-80% FTP WarmUp\n\n3x\n- 10m 100% FTP Threshold\n- 5m 55% FTP Recovery\n\n- 10m Ramp 70-45% FTP CoolDown"),
            ("VO2max 4x4", "Klasični 4x4 minute na VO2max",
             "- 15m Ramp 55-80% FTP WarmUp\n\n4x\n- 4m 115% FTP VO2 Max\n- 4m 50% FTP Recovery\n\n- 10m Ramp 70-45% FTP CoolDown"),
            ("VO2max 5x3", "Kratki VO2max intervali",
             "- 15m Ramp 55-80% FTP WarmUp\n\n5x\n- 3m 120% FTP VO2 Max\n- 3m 50% FTP Recovery\n\n- 10m Ramp 70-45% FTP CoolDown"),
            ("Over/Under", "Izmjena nad i pod pragom",
             "- 15m Ramp 60-85% FTP WarmUp\n\n2x\n- 6m 95% FTP Threshold\n- 2m 105% FTP VO2 Max\n- 6m 95% FTP Threshold\n- 2m 105% FTP VO2 Max\n- 6m 95% FTP Threshold\n- 6m 55% FTP Recovery\n\n- 10m Ramp 70-40% FTP CoolDown"),
            ("Sprint 5x30s", "Kratki maksimalni sprintevi",
             "- 15m Ramp 55-75% FTP WarmUp\n\n5x\n- 30s 150% FTP Sprint\n- 4m 50% FTP Recovery\n\n- 10m Ramp 70-45% FTP CoolDown"),
            ("Slope climb", "Simulacija uspona na nagibu",
             "- 10m Ramp 55-70% FTP WarmUp\n\n3x\n- 15m 80% FTP #3.5% SLOPE# Climb\n- 5m 55% FTP Recovery\n\n- 10m Ramp 65-45% FTP CoolDown"),
        ]

        for title, desc, template in TEMPLATES:
            card = QFrame()
            card.setObjectName("deviceRow")
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(10, 7, 10, 7)
            c_lay.setSpacing(2)
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-size: 12px; font-weight: 500;")
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("font-size: 10px; color: #888;")
            c_lay.addWidget(title_lbl)
            c_lay.addWidget(desc_lbl)
            inner_lay.addWidget(card)
            def _click(e, t=template, n=title):
                editor.setPlainText(t)
                editor._template_name = n
                tabs.setCurrentIndex(0)
            card.mousePressEvent = _click
        inner_lay.addStretch()

        # ── Gumbi ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Odustani")
        cancel_btn.clicked.connect(dlg.reject)

        format_btn = QPushButton("? Format")
        format_btn.setStyleSheet("font-size: 10px;")
        format_btn.clicked.connect(self._on_show_format_help)

        save_btn = QPushButton("Spremi TXT")
        def _save_txt():
            text = editor.toPlainText().strip()
            if not text:
                error_lbl.setText("Nema teksta za snimanje.")
                tabs.setCurrentIndex(0)
                return
            from PyQt6.QtWidgets import QFileDialog
            name = getattr(editor, "_template_name", "workout")
            safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
            path_out, _ = QFileDialog.getSaveFileName(
                dlg, "Spremi workout", f"{safe_name}.txt", "Text Files (*.txt)"
            )
            if path_out:
                open(path_out, "w", encoding="utf-8").write(text)
        save_btn.clicked.connect(_save_txt)

        ok_btn = QPushButton("Učitaj workout")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet("font-weight: 600;")

        def _try_load():
            text = editor.toPlainText().strip()
            if not text:
                tabs.setCurrentIndex(0)
                error_lbl.setText("Nema teksta za parsiranje.")
                return
            try:
                from workout.parser import DescriptionParser
                name = getattr(editor, "_template_name", "Workout")
                workout = DescriptionParser().parse(text, ftp=ftp, name=name)
                if not workout.intervals:
                    tabs.setCurrentIndex(0)
                    error_lbl.setText("Neispravan format — nisu pronađeni intervali.")
                    return
                self._load_workout(workout)
                dlg.accept()
            except Exception as e:
                tabs.setCurrentIndex(0)
                error_lbl.setText(f"Neispravan format: {e}")

        ok_btn.clicked.connect(_try_load)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(format_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)
        dlg.exec()

    def _on_load_workout(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Odaberi workout", "",
            "Workout Files (*.zwo *.json *.txt);;ZWO Files (*.zwo);;intervals.icu JSON (*.json);;intervals.icu Text (*.txt)"
        )
        if not path:
            return
        try:
            p = path.lower()
            if p.endswith(".json"):
                from workout.parser import IntervalsParser
                workout = IntervalsParser().parse(path)
            elif p.endswith(".txt"):
                from workout.parser import DescriptionParser
                import os
                text = open(path, encoding="utf-8").read()
                name = os.path.splitext(os.path.basename(path))[0]
                ftp  = self._intervals_ftp()
                workout = DescriptionParser().parse(text, ftp=ftp, name=name)
            else:
                from workout.parser import ZWOParser
                workout = ZWOParser().parse(path)
            self._load_workout(workout)
        except Exception as e:
            import traceback
            print(f"Greška pri učitavanju workota: {e}")
            traceback.print_exc()

    def _load_workout(self, workout: Workout):
        self.player.load(workout)
        self._last_sent_target = None  # reset da se pošalje prvi target odmah
        td = workout.total_duration
        self.power_zone_bar._total_duration = td
        self.hr_zone_bar._total_duration = td
        self.power_zone_bar.reset_time()
        self.hr_zone_bar.reset_time()

        self.workout_name_lbl.setText(workout.name)
        self.workout_type_badge.setText("ERG")
        self.workout_type_badge.setObjectName("badgeSuccess")
        self.lbl_if.setText(f"IF: {workout.intensity_factor}")
        self.lbl_tss.setText(f"TSS: {workout.tss}")
        self.total_lbl.setText(self._fmt(workout.total_duration))
        self.interval_bar.set_intervals(workout.intervals, 0)
        self.interval_bar._cadence_lookup_fn = self._cadence_for_interval
        self.time_axis.set_total_duration(workout.total_duration)
        self.interval_dots.set_intervals(workout.intervals)
        self._prev_interval_idx = 0
        self._interval_elapsed = 0
        self._last_interval_avg_power = 0
        self.free_ctrl.setVisible(False)
        self.workout_ctrl.setVisible(True)
        self.load_btn.setText("Promijeni ↗")
        self.unload_btn2.setVisible(True)
        has_slope = any(getattr(iv, 'slope', None) is not None for iv in workout.intervals)
        self._grade_frame.setVisible(has_slope)
        # Invalidate cache da dobijemo svježe zone s cadence_rpm
        if hasattr(self, '_local_athlete_cache'):
            del self._local_athlete_cache
        # Postavi cadence range za prvi interval
        self._set_cadence_for_current_interval()
        # Makni zlatni rub s Danas tipke
        if self.intervals_today_btn.isEnabled():
            self.intervals_today_btn.setStyleSheet("font-size: 11px;")
        # zaključaj mod gumbe — workout diktira mod automatski
        self.btn_erg.setEnabled(False)
        self.btn_sim.setEnabled(False)
        # sinkroniziraj X os grafa s trajanjem workota
        self.chart_widget.set_workout(workout.total_duration, workout.ftp)
        # automatski prebaci u ERG mod
        self._set_mode(TrainerMode.ERG)
        self._update_cur_int_ui()

    def _on_unload_workout(self):
        self.player.unload()
        self._last_sent_target = None
        self.workout_name_lbl.setText("—")
        self.cur_int_center_lbl.setText("")
        self.cur_int_detail_center_lbl.setText("")
        self.workout_type_badge.setText("")
        self.cadence_gauge.set_cadence_range_direct(0, 0)
        self._cadence_interpolating = False
        self.workout_type_badge.setObjectName("badgeNeutral")
        self.lbl_if.setText("IF: —"); self.lbl_tss.setText("TSS: —")
        self.lbl_cur_int.setText("Interval: —")
        self.total_lbl.setText("—")
        self.interval_bar.set_intervals([], 0)
        self.time_axis.set_total_duration(0)
        self.interval_dots.set_intervals([])
        self.free_ctrl.setVisible(True)
        self.workout_ctrl.setVisible(False)
        self.load_btn.setText("Učitaj ↗")
        self.unload_btn2.setVisible(False)
        self._grade_frame.setVisible(False)
        self.chart_widget.clear_workout()
        # otključaj mod gumbe
        self.btn_erg.setEnabled(True)
        self.btn_sim.setEnabled(True)
        # vrati Slope mod
        self._set_mode(TrainerMode.SIMULATION)
        self._on_stop()

    def _on_connect_trainer(self):
        if self._trainer and self._trainer.state == ConnectionState.CONNECTED:
            run_async(self._disconnect_trainer())
            return

        from ble.scanner_dialog import ScannerDialog, FEC_SERVICE
        dlg = ScannerDialog(self, "Odaberi trenažer", filter_service=FEC_SERVICE)
        dlg.device_selected.connect(self._on_trainer_device_selected)
        dlg.show()

    async def _disconnect_trainer(self):
        await self._trainer.disconnect()
        self._set_trainer_ui(ConnectionState.DISCONNECTED, "")

    def _on_trainer_device_selected(self, address: str, name: str):
        run_async(self._connect_trainer_async(address, name))

    async def _connect_trainer_async(self, address: str, name: str):
        self._trainer_name = name
        self._set_trainer_ui_threadsafe(ConnectionState.CONNECTING, "Spajanje...")
        try:
            from ble.trainer import TacxTrainer
            self._trainer = TacxTrainer(
                on_metrics=self._on_trainer_metrics,
                on_state_change=self._on_trainer_state
            )
            await self._trainer.connect(address)
            self._set_trainer_ui_threadsafe(ConnectionState.CONNECTED, name)
            self._timer.stop()
        except Exception as e:
            self._set_trainer_ui_threadsafe(ConnectionState.DISCONNECTED, "Greška spajanja")
            print(f"BLE greška: {e}")

    def _on_connect_hr(self):
        if self._hr_monitor and self._hr_monitor.connected:
            run_async(self._disconnect_hr())
            return

        from ble.scanner_dialog import ScannerDialog
        # bez filtera — prikazujemo sve BLE uređaje jer pulsmetri imaju razna imena
        dlg = ScannerDialog(self, "Odaberi pulsmetar", filter_service=None)
        dlg.device_selected.connect(self._on_hr_device_selected)
        dlg.show()

    async def _disconnect_hr(self):
        await self._hr_monitor.disconnect()
        self._set_hr_ui_threadsafe(False, "Spoji")

    def _on_hr_device_selected(self, address: str, name: str):
        run_async(self._connect_hr_async(address, name))

    async def _connect_hr_async(self, address: str, name: str):
        try:
            from ble.heartrate import HeartRateMonitor
            self._hr_monitor = HeartRateMonitor(on_hr=self._on_hr_received)
            await self._hr_monitor._connect_async(address)
            self._set_hr_ui_threadsafe(True, name)
        except Exception as e:
            self._set_hr_ui_threadsafe(False, "Greška")
            print(f"HR BLE greška: {e}")

    def _on_trainer_metrics(self, metrics):
        """Callback s pravog trenažera — dolazi iz asyncio threada, mora biti thread-safe."""
        # koristimo Qt signal mehanizam koji je thread-safe
        self._metrics_signal.emit(metrics)

    def _on_trainer_state(self, state: ConnectionState):
        self._state_signal.emit(state)

    def _on_hr_data(self, hr: int):
        self._hr_signal.emit(hr)

    def _on_metrics_received(self, metrics):
        if self._hr_monitor and self._hr_monitor.connected:
            hr = self._hr_monitor.current_hr
            metrics.heart_rate = hr
            if hr > 0:
                self._int_hr_sum += hr
                self._int_hr_cnt += 1
            metrics.interval_avg_hr = round(self._int_hr_sum / self._int_hr_cnt) if self._int_hr_cnt else 0
        self._update_metrics(metrics)
        if self.player.is_active:
            # auto-reset avg kad se interval automatski promijeni
            if self.player._interval_elapsed == 1:
                self._reset_interval_stats()
            self._update_timebar()

    def _on_state_received(self, state):
        name = self._trainer_name if hasattr(self, '_trainer_name') else "Trenažer"
        self._set_trainer_ui(state, name)

    def _on_hr_received(self, hr: int):
        """HR update iz pulsmetra — ažurira gauge direktno."""
        self.hr_gauge.set_value(hr)

    def _set_trainer_ui_threadsafe(self, state: ConnectionState, label: str):
        """Thread-safe wrapper — može se zvati iz asyncio threada."""
        self._state_signal.emit(state)
        # label update kroz timer
        QTimer.singleShot(0, lambda: self._set_trainer_ui(state, label))

    def _set_hr_ui_threadsafe(self, connected: bool, label: str):
        # emitiramo signal koji nosi i ime uređaja
        self._hr_name_signal.emit(connected, label)

    def _set_trainer_ui(self, state: ConnectionState, label: str):
        connected = state == ConnectionState.CONNECTED
        connecting = state == ConnectionState.CONNECTING

        self.status_dot.setObjectName(
            "statusDotConnected" if connected else "statusDotDisconnected"
        )
        self._trainer_display_name = label if connected else ""
        self._update_devices_label()
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

        self._trainer_tag.setText("Spojeno" if connected else "Spoji")
        if connected:
            self._trainer_tag.setStyleSheet("background:#C0DD97;color:#27500A;font-size:10px;padding:2px 6px;border-radius:4px;")
        elif connecting:
            self._trainer_tag.setStyleSheet("background:#FAC775;color:#633806;font-size:10px;padding:2px 6px;border-radius:4px;")
        else:
            self._trainer_tag.setStyleSheet("background:#e8e8e8;color:#666;font-size:10px;padding:2px 6px;border-radius:4px;")

        if connected and self._timer.isActive() and not self._playing:
            QTimer.singleShot(0, self._timer.stop)
        elif not connected and self._playing and not self._timer.isActive():
            QTimer.singleShot(0, self._timer.start)

    def _set_hr_ui(self, connected: bool, label: str):
        self._hr_display_name = label if connected else ""
        self._update_devices_label()
        self._hr_tag.setText("Spojeno" if connected else label)
        if connected:
            self._hr_tag.setStyleSheet("background:#C0DD97;color:#27500A;font-size:10px;padding:2px 6px;border-radius:4px;")
        else:
            self._hr_tag.setStyleSheet("background:#e8e8e8;color:#666;font-size:10px;padding:2px 6px;border-radius:4px;")

    def _update_devices_label(self):
        from PyQt6.QtCore import Qt
        trainer = getattr(self, "_trainer_display_name", "")
        hr_name = getattr(self, "_hr_display_name", "")
        hr_connected = bool(hr_name)
        heart = '<span style="color:#dd0447;">♥</span>' if hr_connected else '<span style="color:#555;">♥</span>'
        parts = []
        if trainer: parts.append(trainer)
        if hr_name: parts.append(f"{heart} {hr_name}")
        elif hr_connected is False:
            pass
        text = "  ·  ".join(parts) if parts else "Devices"
        self.status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.status_lbl.setText(text)

    # ------------------------------------------------------------------ Style

    def _toggle_dark_mode(self):
        self._dark_mode = not self._dark_mode
        self._apply_stylesheet()
        self.theme_btn.setText("☀ Light" if self._dark_mode else "☾ Dark")

    def _apply_stylesheet(self):
        if self._dark_mode:
            self.setStyleSheet("""
                QMainWindow, QWidget { color: #d0ccc0; background: transparent; }
                #topbar { background: #0d0f14; border-bottom: 1px solid #1e2230; }
                #appTitle { font-size: 14px; font-weight: 500; color: #d0ccc0; }
                #statusDotDisconnected { color: #dd0447; font-size: 10px; }
                #statusDotConnected { color: #009e80; font-size: 10px; }
                #statusLabel { font-size: 12px; color: #505868; }
                #metricCard {
                    background: #0e1015;
                    border: 1px solid #1e2230;
                    border-top: 2px solid #c8a84b;
                    border-radius: 6px;
                }
                #metricCardSecondary {
                    background: #0e1015;
                    border: 1px solid #1e2230;
                    border-radius: 6px;
                }
                #metricLabel { font-size: 10px; color: #505868; letter-spacing: 1px; }
                #metricValue { font-size: 22px; font-weight: 500; color: #e8e0d0; font-family: "Courier New"; }
                #metricValueSecondary { font-size: 18px; font-weight: 500; color: #606878; font-family: "Courier New"; }
                #metricUnit { font-size: 10px; color: #c8a84b; }
                #card {
                    background: #0e1015;
                    border: 1px solid #1e2230;
                    border-radius: 8px;
                }
                #workoutName { font-size: 12px; font-weight: 500; color: #d0ccc0; }
                #statLabel { font-size: 10px; color: #404858; }
                #rightPanel { background: #0d0f14; border-left: 1px solid #1e2230; }
                #sectionLabel { font-size: 9px; font-weight: 500; color: #3a4050; letter-spacing: 2px; }
                #modeActive {
                    background: #141820;
                    color: #c8a84b;
                    border: 1px solid #c8a84b;
                    font-size: 11px; border-radius: 6px; padding: 5px;
                    font-weight: 500;
                }
                #modeInactive {
                    background: #0e1015;
                    color: #404858;
                    border: 1px solid #1e2230;
                    font-size: 11px; border-radius: 6px; padding: 5px;
                }
                #modeActive:hover { background: #1a2030; }
                #modeInactive:hover { background: #141820; color: #707888; }
                #modeActive:disabled, #modeInactive:disabled { opacity: 0.3; }
                #ctrlVal { font-size: 11px; font-weight: 500; color: #d0ccc0; font-family: "Courier New"; }
                #ftpBox { background: #0e1015; border: 1px solid #1e2230; border-radius: 6px; }
                #ftpVal { font-size: 16px; font-weight: 500; color: #d0ccc0; }
                #deviceRow { background: #0e1015; border: 1px solid #1e2230; border-radius: 6px; }
                #deviceRow:hover { background: #141820; border-color: #2a2d3a; }
                QSlider::groove:horizontal { background: #1e2230; height: 4px; border-radius: 2px; }
                QSlider::handle:horizontal { background: #c8a84b; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
                QSlider::sub-page:horizontal { background: #c8a84b; border-radius: 2px; opacity: 0.6; }
                #transport { background: #0d0f14; border-top: 1px solid #1e2230; }
                QPushButton {
                    background: #0e1015;
                    color: #9098a8;
                    border: 1px solid #1e2230;
                    border-radius: 6px; padding: 4px 10px;
                }
                QPushButton:hover { background: #141820; color: #d0ccc0; border-color: #2a2d3a; }
                QPushButton:pressed { background: #0a0c10; }
                #playBtn { border-radius: 18px; border: 1px solid #2a2d3a; background: #0e1015; font-size: 14px; color: #d0ccc0; }
                #playBtn:hover { background: #141820; border-color: #c8a84b; }
                #stopBtn { border: 1px solid #4a1520; background: #160810; color: #dd0447; font-size: 14px; border-radius: 6px; }
                #stopBtn:hover { background: #200a14; border-color: #dd0447; }
                #timerLabel { font-size: 14px; font-weight: 500; font-family: "Courier New"; color: #d0ccc0; }
                #progressBg { background: #1e2230; border-radius: 2px; }
                #progressFill { background: #c8a84b; border-radius: 2px; }
                #intensityVal { font-size: 12px; font-weight: 500; color: #d0ccc0; font-family: "Courier New"; }
                QListWidget { background: #0e1015; color: #d0ccc0; border: 1px solid #1e2230; }
                QListWidget::item:selected { background: #141820; color: #c8a84b; }
                QListWidget::item:hover { background: #0e1015; }
                QScrollBar:vertical { background: #0e1015; width: 6px; }
                QScrollBar::handle:vertical { background: #2a2d3a; border-radius: 3px; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
                QTabWidget::pane { border: 1px solid #1e2230; background: #0e1015; border-radius: 6px; }
                QTabBar::tab { background: #0d0f14; color: #505868; border: 1px solid #1e2230; padding: 5px 12px; border-radius: 4px 4px 0 0; }
                QTabBar::tab:selected { background: #0e1015; color: #c8a84b; border-bottom: 2px solid #c8a84b; }
                QTabBar::tab:hover { color: #9098a8; background: #141820; }
                QTextEdit { background: #080a0e; color: #d0ccc0; border: 1px solid #1e2230; border-radius: 4px; font-family: "Courier New"; }
                QDialog { background: #0e1015; }
                QLabel { color: #9098a8; }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow { background: #f0efea; }
                #topbar { background: white; border-bottom: 1px solid #e0e0e0; }
                #appTitle { font-size: 14px; font-weight: 500; }
                #statusDotDisconnected { color: #E24B4A; font-size: 10px; }
                #statusDotConnected { color: #639922; font-size: 10px; }
                #statusLabel { font-size: 12px; color: #666; }
                #metricCard { background: #e8e7e2; border-radius: 6px; }
                #metricCardSecondary { background: #f0efea; border: 1px solid #ddd; border-radius: 6px; }
                #metricLabel { font-size: 10px; color: #888; }
                #metricValue { font-size: 20px; font-weight: 500; }
                #metricValueSecondary { font-size: 18px; font-weight: 500; color: #888; }
                #metricUnit { font-size: 10px; color: #aaa; }
                #card { background: white; border: 1px solid #e0e0e0; border-radius: 8px; }
                #chartView { background: white; border: 1px solid #e0e0e0; border-radius: 8px; }
                #workoutName { font-size: 12px; font-weight: 500; }
                #statLabel { font-size: 10px; color: #888; }
                #rightPanel { background: white; border-left: 1px solid #e0e0e0; }
                #sectionLabel { font-size: 10px; font-weight: 500; color: #999; letter-spacing: 1px; }
                #modeActive { background: #E6F1FB; color: #185FA5; border: 1px solid #B5D4F4; font-size: 11px; border-radius: 6px; padding: 5px; }
                #modeInactive { background: white; color: #999; border: 1px solid #ddd; font-size: 11px; border-radius: 6px; padding: 5px; }
                #modeActive:hover, #modeInactive:hover { background: #f5f5f5; }
                #modeActive:disabled, #modeInactive:disabled { opacity: 0.4; }
                #ctrlVal { font-size: 11px; font-weight: 500; }
                #ftpBox { background: #f0efea; border-radius: 6px; }
                #ftpVal { font-size: 16px; font-weight: 500; }
                #deviceRow { background: #f0efea; border-radius: 6px; }
                #transport { background: white; border-top: 1px solid #e0e0e0; }
                #playBtn { border-radius: 18px; border: 1px solid #ccc; background: white; font-size: 14px; }
                #playBtn:hover { background: #f5f5f5; }
                #stopBtn { border: 1px solid #F7C1C1; background: #FCEBEB; color: #A32D2D; font-size: 14px; border-radius: 6px; }
                #timerLabel { font-size: 14px; font-weight: 500; font-family: monospace; }
                #progressBg { background: #e0e0e0; border-radius: 2px; }
                #progressFill { background: #185FA5; border-radius: 2px; }
                #intensityVal { font-size: 12px; font-weight: 500; }
            """)
