from models.data import Workout, WorkoutInterval, MetricsData


class WorkoutPlayer:
    """
    Upravlja reprodukcijom workota — praćenje intervala,
    ERG targets, intenzitet.
    """

    def __init__(self):
        self.workout: Workout | None = None
        self.elapsed: int = 0          # ukupno sekundi od starta
        self.current_idx: int = 0      # indeks trenutnog intervala
        self.intensity_pct: int = 100  # 50-150%
        self.is_active: bool = False

        self._interval_elapsed: int = 0
        self._interval_start: int = 0
        self._wall_start: float = 0.0  # time.time() pri startu

    def load(self, workout: Workout):
        self.workout = workout
        self.reset()

    def unload(self):
        self.workout = None
        self.reset()

    def reset(self):
        self.elapsed = 0
        self.current_idx = 0
        self._interval_elapsed = 0
        self._interval_start = 0
        self._wall_start = 0.0
        self.is_active = False

    def tick(self):
        """Poziva se svake sekunde dok trening traje."""
        import time
        if not self.workout or not self.is_active:
            return

        # Ako je prvi tick, postavi wall clock start
        if self._wall_start == 0.0:
            self._wall_start = time.time() - self.elapsed

        # Elapsed baziran na stvarnom vremenu, ne tick brojaču
        self.elapsed = int(time.time() - self._wall_start)
        self._interval_elapsed = self.elapsed - self._interval_start

        # provjeri treba li prijeći na sljedeći interval
        current = self.current_interval
        if current and self._interval_elapsed >= current.duration:
            self._next_interval_auto()

    def _next_interval_auto(self):
        if self.current_idx + 1 < len(self.workout.intervals):
            self.current_idx += 1
            self._interval_elapsed = 0
            self._interval_start = self.elapsed
        else:
            self.is_active = False  # workout završen

    def jump_to_interval(self, idx: int):
        import time
        if not self.workout:
            return
        idx = max(0, min(len(self.workout.intervals) - 1, idx))
        self.current_idx = idx
        # elapsed ostaje — bilježi stvarno odrađeno vrijeme
        # interval_start = trenutni elapsed da interval počne od 0
        self._interval_start = self.elapsed
        self._interval_elapsed = 0

    def prev_interval(self):
        self.jump_to_interval(self.current_idx - 1)

    def next_interval(self):
        self.jump_to_interval(self.current_idx + 1)

    def change_intensity(self, delta: int):
        self.intensity_pct = max(50, min(150, self.intensity_pct + delta))

    @property
    def current_interval(self) -> WorkoutInterval | None:
        if not self.workout or not self.workout.intervals:
            return None
        return self.workout.intervals[self.current_idx]

    @property
    def is_slope_step(self) -> bool:
        """True ako trenutni interval treba slope mod umjesto ERG."""
        iv = self.current_interval
        return iv is not None and iv.slope is not None

    @property
    def target_slope(self) -> float | None:
        """Nagib u % za slope mod, ili None ako je ERG korak."""
        iv = self.current_interval
        if iv is None or iv.slope is None:
            return None
        return iv.slope

    @property
    def target_power(self) -> int:
        """Ciljna snaga u Wattima — za ramp/warmup/cooldown linearno interpolira.
        Vraća 0 za slope korake (trenažer se kontrolira nagibom)."""
        if not self.workout or not self.current_interval:
            return 0
        iv = self.current_interval

        # slope koraci — ERG target nije relevantan
        if iv.slope is not None:
            return 0

        pct = iv.power_pct

        # za ramp tipove: linearna interpolacija po napretku unutar intervala
        if iv.type in ("ramp", "warmup", "cooldown") and iv.duration > 0:
            progress = self._interval_elapsed / iv.duration
            progress = max(0.0, min(1.0, progress))
            pct = iv.power_pct + (iv.power_pct_end - iv.power_pct) * progress

        return round(
            self.workout.ftp * pct * self.intensity_pct / 100
        )

    @property
    def interval_remaining(self) -> int:
        """Sekundi do kraja trenutnog intervala."""
        if not self.current_interval:
            return 0
        return max(0, self.current_interval.duration - self._interval_elapsed)

    @property
    def total_remaining(self) -> int:
        """Sekundi do kraja workota."""
        if not self.workout:
            return 0
        return max(0, self.workout.total_duration - self.elapsed)

    @property
    def progress(self) -> float:
        """0.0 - 1.0"""
        if not self.workout or self.workout.total_duration == 0:
            return 0.0
        return min(1.0, self.elapsed / self.workout.total_duration)

    @property
    def interval_label(self) -> str:
        if not self.workout:
            return "—"
        return f"{self.current_idx + 1}/{len(self.workout.intervals)}"
