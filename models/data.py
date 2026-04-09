from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class TrainerMode(Enum):
    ERG = "erg"
    SIMULATION = "simulation"


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    CONNECTED = "connected"


@dataclass
class MetricsData:
    power: int = 0            # trenutna snaga W
    power_3s: int = 0         # 3s rolling average W
    cadence: int = 0          # rpm
    heart_rate: int = 0       # bpm
    speed: float = 0.0        # km/h
    grade: float = 0.0        # % nagib
    distance: float = 0.0     # km

    interval_avg_power: int = 0
    interval_avg_hr: int = 0
    target_power: int = 0
    target_grade: float = 0.0

    # Pedal balance i smoothness (iz CPS karakteristike)
    balance_left: float = 0.0    # % lijeva noga (0 = nema podatka)
    smoothness_left: float = 0.0   # % glatkoća lijeva (0 = nema podatka)
    smoothness_right: float = 0.0  # % glatkoća desna (0 = nema podatka)


@dataclass
class WorkoutInterval:
    name: str
    duration: int             # sekunde
    power_pct: float          # % FTP start (0.0 - 2.0)
    power_pct_end: float = 0.0  # % FTP end (isti kao start za steady, različit za ramp)
    type: str = "steadystate"
    slope: float | None = None  # ako nije None → slope mod (%), ignorira power
    text: str = ""              # originalni text tag iz intervals.icu

    def __post_init__(self):
        # ako power_pct_end nije postavljen, kopiramo power_pct
        if self.power_pct_end == 0.0 and self.power_pct != 0.0:
            self.power_pct_end = self.power_pct


@dataclass
class Workout:
    name: str
    description: str = ""
    author: str = ""
    ftp: int = 240
    intervals: list = field(default_factory=list)

    @property
    def total_duration(self) -> int:
        return sum(iv.duration for iv in self.intervals)

    @property
    def tss(self) -> float:
        """Aproksimacija TSS-a"""
        total = 0.0
        for iv in self.intervals:
            total += (iv.duration / 3600) * (iv.power_pct ** 2) * 100
        return round(total, 1)

    @property
    def intensity_factor(self) -> float:
        """Weighted average power pct"""
        if not self.intervals:
            return 0.0
        total_w = sum(iv.power_pct ** 4 * iv.duration for iv in self.intervals)
        total_d = sum(iv.duration for iv in self.intervals)
        return round((total_w / total_d) ** 0.25, 2) if total_d > 0 else 0.0
