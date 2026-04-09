from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QSpinBox, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt


CADENCE_ZONE_LABELS = [
    ("Recovery (Z1)",        "recovery"),
    ("Endurance (Z2)",       "endurance"),
    ("Tempo / Threshold (Z3-Z4)", "threshold"),
    ("VO2 Max (Z5-Z6)",      "vo2 max"),
    ("Anaerobic / Sprint",   "anaerobic"),
]

DEFAULT_CADENCE_ZONES = {
    "recovery":    [70,  85],
    "endurance":   [80,  95],
    "threshold":   [88, 100],
    "vo2 max":     [90, 110],
    "anaerobic":   [90, 110],
}


class IntervalsSettingsDialog(QDialog):

    def __init__(self, parent=None, athlete_id: str = "", api_key: str = "",
                 tolerance: int = 15, cadence_zones: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Postavke")
        self.setMinimumWidth(460)
        self.setModal(True)

        self.athlete_id  = athlete_id
        self.api_key     = api_key
        self.tolerance   = tolerance
        self.cadence_zones = cadence_zones or dict(DEFAULT_CADENCE_ZONES)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tabs = QTabWidget()
        root.addWidget(tabs, stretch=1)

        # ── Tab 1: intervals.icu ──────────────────────────────────
        tab_api = QWidget()
        lay = QVBoxLayout(tab_api)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 16, 20, 16)

        title = QLabel("Poveži s intervals.icu")
        title.setStyleSheet("font-size: 13px; font-weight: 500;")
        lay.addWidget(title)

        info = QLabel("API key: intervals.icu → Settings → Developer Settings")
        info.setStyleSheet("font-size: 10px; color: #666;")
        lay.addWidget(info)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(line)

        lay.addWidget(QLabel("Athlete ID:"))
        self.id_input = QLineEdit(athlete_id)
        self.id_input.setPlaceholderText("npr. i12345")
        lay.addWidget(self.id_input)

        lay.addWidget(QLabel("API Key:"))
        self.key_input = QLineEdit(api_key)
        self.key_input.setPlaceholderText("Tvoj intervals.icu API key")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_input)
        self.toggle_btn = QPushButton("Prikaži")
        self.toggle_btn.setFixedWidth(70)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._toggle_key)
        key_row.addWidget(self.toggle_btn)
        lay.addLayout(key_row)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 11px;")
        self.status_lbl.setWordWrap(True)
        lay.addWidget(self.status_lbl)
        lay.addStretch()
        tabs.addTab(tab_api, "intervals.icu")

        # ── Tab 2: Slope tolerancija ──────────────────────────────
        tab_slope = QWidget()
        sl = QVBoxLayout(tab_slope)
        sl.setSpacing(10)
        sl.setContentsMargins(20, 16, 20, 16)

        sl.addWidget(QLabel("Tolerancija za slope signal (±W):"))
        tol_row = QHBoxLayout()
        self.tol_spin = QSpinBox()
        self.tol_spin.setRange(5, 50)
        self.tol_spin.setValue(tolerance)
        self.tol_spin.setSuffix(" W")
        tol_row.addWidget(self.tol_spin)
        tol_row.addStretch()
        sl.addLayout(tol_row)

        hint = QLabel("Lampice se pale kad je snaga izvan ovog raspona od referentne.\nRecovery i Cooldown intervali nemaju preporučenu kadencu.")
        hint.setStyleSheet("font-size: 10px; color: #666;")
        hint.setWordWrap(True)
        sl.addWidget(hint)
        sl.addStretch()
        tabs.addTab(tab_slope, "Slope signal")

        # ── Tab 3: Kadenca ────────────────────────────────────────
        tab_cad = QWidget()
        cl = QVBoxLayout(tab_cad)
        cl.setSpacing(8)
        cl.setContentsMargins(20, 16, 20, 16)

        cl.addWidget(QLabel("Optimalni raspon kadence po zoni (rpm):"))

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Zona"), stretch=3)
        lbl_min = QLabel("Od"); lbl_min.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_max = QLabel("Do"); lbl_max.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.addWidget(lbl_min, stretch=1)
        hdr.addWidget(lbl_max, stretch=1)
        cl.addLayout(hdr)

        self._cad_spins = {}
        for label, key in CADENCE_ZONE_LABELS:
            row = QHBoxLayout()
            row.addWidget(QLabel(label), stretch=3)
            lo, hi = self.cadence_zones.get(key, DEFAULT_CADENCE_ZONES.get(key, [80, 100]))
            spin_lo = QSpinBox(); spin_lo.setRange(40, 150); spin_lo.setValue(lo); spin_lo.setSuffix(" rpm")
            spin_hi = QSpinBox(); spin_hi.setRange(40, 160); spin_hi.setValue(hi); spin_hi.setSuffix(" rpm")
            row.addWidget(spin_lo, stretch=1)
            row.addWidget(spin_hi, stretch=1)
            cl.addLayout(row)
            self._cad_spins[key] = (spin_lo, spin_hi)

        cl.addStretch()
        tabs.addTab(tab_cad, "Kadenca")

        # ── Gumbi ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 8, 16, 12)
        cancel_btn = QPushButton("Odustani")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Spremi")
        save_btn.setDefault(True)
        save_btn.setStyleSheet("font-weight: 500;")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    def _toggle_key(self, checked: bool):
        self.key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        self.toggle_btn.setText("Sakrij" if checked else "Prikaži")

    def _on_save(self):
        aid = self.id_input.text().strip()
        key = self.key_input.text().strip()
        if not aid or not key:
            self.status_lbl.setStyleSheet("font-size: 11px; color: #E24B4A;")
            self.status_lbl.setText("Molim unesi Athlete ID i API Key.")
            return
        self.athlete_id  = aid
        self.api_key     = key
        self.tolerance   = self.tol_spin.value()
        self.cadence_zones = {
            key: [lo.value(), hi.value()]
            for key, (lo, hi) in self._cad_spins.items()
        }
        self.accept()

    def get_credentials(self) -> tuple[str, str]:
        return self.id_input.text().strip(), self.key_input.text().strip()
