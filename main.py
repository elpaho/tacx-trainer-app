import sys
import os
import asyncio
import threading

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PyQt6.QtCore import QTimer, Qt, QObject, pyqtSignal
from version import VERSION


class UpdateChecker(QObject):
    """Qt objekt koji emitira signal iz background threada."""
    update_available = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def check_in_background(self):
        def _check():
            try:
                from updater import check_for_update
                new_version = check_for_update(VERSION)
                if new_version:
                    self.update_available.emit(new_version)
            except Exception as e:
                print(f"[update] Greška pri provjeri: {e}")
        threading.Thread(target=_check, daemon=True).start()


def _ask_update(new_version):
    msg = QMessageBox()
    msg.setWindowTitle("Dostupno ažuriranje")
    msg.setText(f"Nova verzija <b>{new_version}</b> je dostupna.\n\nTrenutna verzija: {VERSION}")
    msg.setInformativeText("Želiš li ažurirati i restartati aplikaciju?")
    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    msg.setDefaultButton(QMessageBox.StandardButton.Yes)
    if msg.exec() != QMessageBox.StandardButton.Yes:
        return

    progress = QProgressDialog("Preuzimanje ažuriranja...", None, 0, 100)
    progress.setWindowTitle("Ažuriranje")
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)
    progress.show()

    def _on_progress(pct):
        def _update():
            if pct < 0:
                # Nema Content-Length — indeterminate (0,0)
                progress.setMaximum(0)
            else:
                if progress.maximum() == 0:
                    progress.setMaximum(100)
                progress.setValue(pct)
        QTimer.singleShot(0, _update)

    def _download():
        from updater import download_and_install, restart_app
        ok = download_and_install(on_progress=_on_progress)
        QTimer.singleShot(0, lambda: _done(ok))

    def _done(ok):
        progress.close()
        if ok:
            QMessageBox.information(None, "Ažuriranje završeno",
                                    "Ažuriranje je uspješno. Aplikacija će se restartati.")
            from updater import restart_app
            restart_app()
        else:
            QMessageBox.warning(None, "Greška",
                                "Ažuriranje nije uspjelo. Pokušaj ručno preuzeti novu verziju.")

    threading.Thread(target=_download, daemon=True).start()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Tacx Neo 2T Controller")
    app.setOrganizationName("TacxApp")

    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

    import builtins
    builtins._asyncio_loop = loop

    from ui.main_window import MainWindow
    window = MainWindow()
    window.resize(1280, 720)
    window.show()

    # Update checker — signal/slot garantira Qt thread sigurnost
    checker = UpdateChecker()
    checker.update_available.connect(_ask_update)
    QTimer.singleShot(3000, checker.check_in_background)

    # Drži referencu da GC ne uništi checker
    app._update_checker = checker

    ret = app.exec()
    loop.call_soon_threadsafe(loop.stop)
    sys.exit(ret)


if __name__ == "__main__":
    main()
