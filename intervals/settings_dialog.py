from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QSpinBox,
    QTabWidget, QWidget, QScrollArea
)
from PyQt6.QtCore import Qt


# Defaultne kadence po power zoni (1 vrijednost)
DEFAULT_ZONE_CADENCE = [75, 85, 88, 90, 95, 100, 105]


class IntervalsSettingsDialog(QDialog):

    def __init__(self, parent=None, athlete_id: str = "", api_key: str = "",
                 tolerance: int = 15,
                 local_ftp: int = 0, local_hr_max: int = 0,
                 local_power_zones: list = None, local_hr_zones: list = None,
                 cadence_tolerance: int = 5):
        super().__init__(parent)
        self.setWindowTitle("Postavke")
        self.setMinimumWidth(540)
        self.setMinimumHeight(640)
        self.setModal(True)

        self.athlete_id        = athlete_id
        self.api_key           = api_key
        self.tolerance         = tolerance
        self.local_ftp         = local_ftp
        self.local_hr_max      = local_hr_max
        self.local_power_zones = local_power_zones or []
        self.local_hr_zones    = local_hr_zones or []
        self.cadence_tolerance = cadence_tolerance

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

        # ── Tab 2: Slope signal ───────────────────────────────────
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
        hint = QLabel("Lampice se pale kad je snaga izvan ovog raspona od referentne.")
        hint.setStyleSheet("font-size: 10px; color: #666;")
        hint.setWordWrap(True)
        sl.addWidget(hint)
        sl.addStretch()
        tabs.addTab(tab_slope, "Slope signal")

        # ── Tab 3: Zone ───────────────────────────────────────────
        tab_zones = QWidget()
        zl = QVBoxLayout(tab_zones)
        zl.setSpacing(8)
        zl.setContentsMargins(20, 12, 20, 12)

        info_z = QLabel(
            "Zone se učitavaju s intervals.icu. Ovdje ih možeš ručno postaviti "
            "ili urediti kao fallback kad nema pristupa internetu."
        )
        info_z.setStyleSheet("font-size: 10px; color: #666;")
        info_z.setWordWrap(True)
        zl.addWidget(info_z)

        base_row = QHBoxLayout()
        base_row.addWidget(QLabel("FTP:"))
        self.local_ftp_spin = QSpinBox()
        self.local_ftp_spin.setRange(0, 600)
        self.local_ftp_spin.setValue(local_ftp)
        self.local_ftp_spin.setSuffix(" W")
        self.local_ftp_spin.setSpecialValueText("—")
        self.local_ftp_spin.setFixedWidth(90)
        base_row.addWidget(self.local_ftp_spin)
        base_row.addSpacing(20)
        base_row.addWidget(QLabel("HR max:"))
        self.local_hr_spin = QSpinBox()
        self.local_hr_spin.setRange(0, 230)
        self.local_hr_spin.setValue(local_hr_max)
        self.local_hr_spin.setSuffix(" bpm")
        self.local_hr_spin.setSpecialValueText("—")
        self.local_hr_spin.setFixedWidth(110)
        base_row.addWidget(self.local_hr_spin)
        base_row.addStretch()
        zl.addLayout(base_row)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        zl.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_w = QWidget()
        scroll_lay = QVBoxLayout(scroll_w)
        scroll_lay.setSpacing(4)
        scroll_lay.setContentsMargins(0, 2, 0, 2)

        # Power zone header
        pw_hdr = QLabel("Power zone")
        pw_hdr.setStyleSheet("font-size: 11px; font-weight: 500; color: #c8a84b;")
        scroll_lay.addWidget(pw_hdr)

        hdr_pw = QHBoxLayout()
        for h, s in [("", 1), ("Od (W)", 2), ("Do (W)", 2), ("Kadenca", 2)]:
            l = QLabel(h); l.setStyleSheet("font-size: 10px; color: #666;")
            hdr_pw.addWidget(l, stretch=s)
        scroll_lay.addLayout(hdr_pw)

        self._pz_spins = []
        pw_zones  = local_power_zones or []
        pw_names  = ["Z1","Z2","Z3","Z4","Z5","Z6","Z7"]
        pw_colors = ["#009e80","#009e00","#ffcb0e","#ff7f0e","#dd0447","#6633cc","#504861"]

        for i in range(7):
            row = QHBoxLayout()
            z = pw_zones[i] if i < len(pw_zones) else {}
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {pw_colors[i]}; font-size: 14px;")
            dot.setFixedWidth(18)
            row.addWidget(dot)
            lbl = QLabel(pw_names[i])
            lbl.setStyleSheet("font-size: 11px;")
            lbl.setFixedWidth(22)
            row.addWidget(lbl)

            spin_min = QSpinBox(); spin_min.setRange(0, 2000)
            spin_min.setValue(z.get("min_val", 0)); spin_min.setSuffix(" W")
            spin_max = QSpinBox(); spin_max.setRange(0, 2000)
            spin_max.setValue(z.get("max_val", 0)); spin_max.setSuffix(" W")
            if i == 6:
                spin_max.setSpecialValueText("∞")
                spin_max.setValue(z.get("max_val", 600))

            default_cad = DEFAULT_ZONE_CADENCE[i] if i < len(DEFAULT_ZONE_CADENCE) else 90
            spin_cad = QSpinBox(); spin_cad.setRange(40, 160)
            spin_cad.setValue(z.get("cadence_rpm", default_cad))
            spin_cad.setSuffix(" rpm")

            row.addWidget(spin_min, stretch=2)
            row.addWidget(spin_max, stretch=2)
            row.addWidget(spin_cad, stretch=2)
            scroll_lay.addLayout(row)
            self._pz_spins.append((spin_min, spin_max, spin_cad, pw_names[i], pw_colors[i]))

        self._pz_updating = False
        for i, (smin, smax, scad, _, _) in enumerate(self._pz_spins):
            smax.valueChanged.connect(lambda v, ix=i: self._pz_max_changed(ix, v))
            smin.valueChanged.connect(lambda v, ix=i: self._pz_min_changed(ix, v))

        scroll_lay.addSpacing(8)

        # HR zone header
        hr_hdr = QLabel("HR zone")
        hr_hdr.setStyleSheet("font-size: 11px; font-weight: 500; color: #dd0447;")
        scroll_lay.addWidget(hr_hdr)

        hdr_hr = QHBoxLayout()
        for h, s in [("", 1), ("Od (bpm)", 2), ("Do (bpm)", 2)]:
            l = QLabel(h); l.setStyleSheet("font-size: 10px; color: #666;")
            hdr_hr.addWidget(l, stretch=s)
        scroll_lay.addLayout(hdr_hr)

        self._hz_spins = []
        hr_zones_data = local_hr_zones or []
        n_hr = max(5, len(hr_zones_data))
        hr_colors = ["#009e80","#009e00","#ffcb0e","#ff7f0e","#dd0447","#6633cc","#504861"]

        for i in range(n_hr):
            row = QHBoxLayout()
            z = hr_zones_data[i] if i < len(hr_zones_data) else {}
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {hr_colors[i % len(hr_colors)]}; font-size: 14px;")
            dot.setFixedWidth(18)
            row.addWidget(dot)
            lbl = QLabel(f"Z{i+1}"); lbl.setStyleSheet("font-size: 11px;")
            row.addWidget(lbl, stretch=1)
            spin_min = QSpinBox(); spin_min.setRange(0, 300)
            spin_min.setValue(z.get("min_val", 0)); spin_min.setSuffix(" bpm")
            spin_max = QSpinBox(); spin_max.setRange(0, 300)
            spin_max.setValue(z.get("max_val", 0)); spin_max.setSuffix(" bpm")
            row.addWidget(spin_min, stretch=2)
            row.addWidget(spin_max, stretch=2)
            scroll_lay.addLayout(row)
            self._hz_spins.append((spin_min, spin_max, f"Z{i+1}", hr_colors[i % len(hr_colors)]))

        self._hz_updating = False
        for i, (smin, smax, _, _) in enumerate(self._hz_spins):
            smax.valueChanged.connect(lambda v, ix=i: self._hz_max_changed(ix, v))
            smin.valueChanged.connect(lambda v, ix=i: self._hz_min_changed(ix, v))

        # Kadenca tolerancija
        scroll_lay.addSpacing(8)
        cad_hdr = QLabel("Kadenca")
        cad_hdr.setStyleSheet("font-size: 11px; font-weight: 500; color: #378ADD;")
        scroll_lay.addWidget(cad_hdr)

        tol_c_row = QHBoxLayout()
        tol_c_row.addWidget(QLabel("Tolerancija (±rpm):"))
        self.cad_tol_spin = QSpinBox()
        self.cad_tol_spin.setRange(1, 20)
        self.cad_tol_spin.setValue(cadence_tolerance)
        self.cad_tol_spin.setSuffix(" rpm")
        tol_c_row.addWidget(self.cad_tol_spin)
        tol_c_hint = QLabel("Optimalni raspon = kadenca zone ± tolerancija")
        tol_c_hint.setStyleSheet("font-size: 10px; color: #666;")
        tol_c_row.addWidget(tol_c_hint, stretch=1)
        scroll_lay.addLayout(tol_c_row)
        scroll_lay.addStretch()

        scroll.setWidget(scroll_w)
        zl.addWidget(scroll, stretch=1)

        self.local_ftp_spin.valueChanged.connect(self._recalc_power_zones)
        self.local_hr_spin.valueChanged.connect(self._recalc_hr_zones)

        tabs.addTab(tab_zones, "Zone")

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

    def _pz_max_changed(self, i, v):
        if self._pz_updating: return
        self._pz_updating = True
        if i + 1 < len(self._pz_spins): self._pz_spins[i+1][0].setValue(v + 1)
        self._pz_updating = False

    def _pz_min_changed(self, i, v):
        if self._pz_updating: return
        self._pz_updating = True
        if i > 0: self._pz_spins[i-1][1].setValue(v - 1)
        self._pz_updating = False

    def _hz_max_changed(self, i, v):
        if self._hz_updating: return
        self._hz_updating = True
        if i + 1 < len(self._hz_spins): self._hz_spins[i+1][0].setValue(v + 1)
        self._hz_updating = False

    def _hz_min_changed(self, i, v):
        if self._hz_updating: return
        self._hz_updating = True
        if i > 0: self._hz_spins[i-1][1].setValue(v - 1)
        self._hz_updating = False

    def _recalc_power_zones(self, ftp):
        if ftp <= 0 or self._pz_updating: return
        pcts = [55, 75, 90, 105, 120, 150]
        self._pz_updating = True
        prev = 0
        for i, (smin, smax, scad, _, _) in enumerate(self._pz_spins):
            if i < len(pcts):
                max_w = round(ftp * pcts[i] / 100)
                smin.setValue(prev + 1 if prev > 0 else 1)
                smax.setValue(max_w)
                prev = max_w
            else:
                smin.setValue(prev + 1)
                smax.setValue(999)
        self._pz_updating = False

    def _recalc_hr_zones(self, hr_max):
        if hr_max <= 0 or self._hz_updating: return
        n = len(self._hz_spins)
        step = 100 // n
        pcts = [step * (i+1) for i in range(n-1)] + [100]
        self._hz_updating = True
        prev = 0
        for i, (smin, smax, _, _) in enumerate(self._hz_spins):
            max_bpm = round(hr_max * pcts[i] / 100)
            smin.setValue(prev + 1 if prev > 0 else 1)
            smax.setValue(max_bpm)
            prev = max_bpm
        self._hz_updating = False

    def _on_save(self):
        aid = self.id_input.text().strip()
        key = self.key_input.text().strip()
        if not aid or not key:
            self.status_lbl.setStyleSheet("font-size: 11px; color: #E24B4A;")
            self.status_lbl.setText("Molim unesi Athlete ID i API Key.")
            return
        self.athlete_id        = aid
        self.api_key           = key
        self.tolerance         = self.tol_spin.value()
        self.cadence_tolerance = self.cad_tol_spin.value()
        self.local_ftp         = self.local_ftp_spin.value()
        self.local_hr_max      = self.local_hr_spin.value()
        self.local_power_zones = [
            {"name": name, "color": color,
             "min_val": smin.value(), "max_val": smax.value(),
             "cadence_rpm": scad.value()}
            for smin, smax, scad, name, color in self._pz_spins
        ]
        self.local_hr_zones = [
            {"name": name, "color": color,
             "min_val": smin.value(), "max_val": smax.value()}
            for smin, smax, name, color in self._hz_spins
        ]
        self.accept()

    def get_credentials(self) -> tuple[str, str]:
        return self.id_input.text().strip(), self.key_input.text().strip()
