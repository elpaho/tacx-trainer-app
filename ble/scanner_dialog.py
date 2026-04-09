import asyncio
import builtins
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from bleak import BleakScanner

FEC_SERVICE = "6e40fec1-b5a3-f393-e0a9-e50e24dcca9e"


def _run_async(coro):
    loop = getattr(builtins, '_asyncio_loop', None)
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, loop)


class ScannerDialog(QDialog):
    device_selected = pyqtSignal(str, str)
    _scan_done = pyqtSignal(list)
    _scan_fail = pyqtSignal(str)

    def __init__(self, parent=None, title="Odaberi BLE uređaj", filter_service=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(420, 340)
        self.setModal(True)
        self.filter_service = filter_service
        self._devices = {}
        self._scan_done.connect(self._update_list)
        self._scan_fail.connect(self._scan_error)
        self._build_ui()
        _run_async(self._do_scan())

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(14, 14, 14, 14)

        self.status_lbl = QLabel("Skeniranje BLE uređaja... (3s)")
        self.status_lbl.setStyleSheet("color: #666; font-size: 12px;")
        lay.addWidget(self.status_lbl)

        self.list = QListWidget()
        self.list.setStyleSheet("""
            QListWidget { border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
            QListWidget::item { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }
            QListWidget::item:selected { background: #E6F1FB; color: #185FA5; }
            QListWidget::item:hover { background: #f5f5f5; }
        """)
        self.list.itemDoubleClicked.connect(self._on_connect_clicked)
        lay.addWidget(self.list)

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("Skeniraj ponovo")
        self.scan_btn.setEnabled(False)
        self.scan_btn.setStyleSheet("""
            QPushButton { padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px; background: white; color: #333; }
            QPushButton:disabled { background: #f5f5f5; color: #aaa; border-color: #ddd; }
            QPushButton:hover:!disabled { background: #eee; }
        """)
        self.scan_btn.clicked.connect(self._on_rescan)

        self.connect_btn = QPushButton("Spoji")
        self.connect_btn.setEnabled(False)
        self.connect_btn.setStyleSheet("padding: 6px 14px; border: 1px solid #B5D4F4; border-radius: 6px; background: #E6F1FB; color: #185FA5; font-weight: 500;")
        self.connect_btn.clicked.connect(self._on_connect_clicked)

        cancel_btn = QPushButton("Odustani")
        cancel_btn.setStyleSheet("padding: 6px 14px; border: 1px solid #ddd; border-radius: 6px; background: white;")
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(self.scan_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.connect_btn)
        lay.addLayout(btn_row)

        self.list.itemSelectionChanged.connect(
            lambda: self.connect_btn.setEnabled(len(self.list.selectedItems()) > 0)
        )

    async def _do_scan(self):
        try:
            discovered = await BleakScanner.discover(timeout=3.0, return_adv=True)
            found = []
            for address, (device, adv) in discovered.items():
                name = device.name or adv.local_name or ""
                if not name:
                    continue
                uuids = [str(u).lower() for u in adv.service_uuids]
                if self.filter_service:
                    uuid_match = self.filter_service.lower() in uuids
                    name_match = any(k in name.upper() for k in
                                     ["TACX", "NEO", "FLUX", "VORTEX", "KICKR",
                                      "SUITO", "DIRETO", "HAMMER", "SNAP"])
                    if not uuid_match and not name_match:
                        continue
                self._devices[address] = name
                found.append((name, address))
            self._scan_done.emit(found)
        except Exception as e:
            self._scan_fail.emit(str(e))

    @pyqtSlot(list)
    def _update_list(self, found):
        self.list.clear()
        for name, address in found:
            item = QListWidgetItem(f"{name}  —  {address}")
            item.setData(Qt.ItemDataRole.UserRole, address)
            self.list.addItem(item)
        if self.list.count() == 0:
            self.status_lbl.setText("Nisu pronađeni uređaji. Provjeri da je uređaj upaljen.")
        else:
            self.status_lbl.setText(f"Pronađeno {self.list.count()} uređaj(a). Odaberi i klikni Spoji.")
        self.scan_btn.setEnabled(True)

    @pyqtSlot(str)
    def _scan_error(self, error):
        self.status_lbl.setText(f"Greška skeniranja: {error}")
        self.scan_btn.setEnabled(True)

    def _on_rescan(self):
        self.list.clear()
        self._devices.clear()
        self.connect_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.status_lbl.setText("Skeniranje... (3s)")
        _run_async(self._do_scan())

    def _on_connect_clicked(self):
        items = self.list.selectedItems()
        if not items:
            return
        address = items[0].data(Qt.ItemDataRole.UserRole)
        name = self._devices.get(address, "Nepoznat")
        self.device_selected.emit(address, name)
        self.accept()
