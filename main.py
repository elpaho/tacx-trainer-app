import sys
import os
import asyncio
import threading

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PyQt6.QtCore import QTimer, Qt, QObject, pyqtSignal
from version import VERSION


class UpdateChecker(QObject):
    """Qt objekt koji emitira signale iz background threadova — thread-safe."""
    update_available = pyqtSignal(str)
    download_done    = pyqtSignal(bool)

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

    def download_in_background(self, on_progress):
        def _dl():
            try:
                from updater import download_and_install
                ok = download_and_install(on_progress=on_progress)
            except Exception as e:
                print(f"[update] Greška pri downloadu: {e}")
                ok = False
            self.download_done.emit(ok)
        threading.Thread(target=_dl, daemon=True).start()


def _ask_update(new_version):
    app = QApplication.instance()
    checker = app._update_checker

    msg = QMessageBox()
    msg.setWindowTitle("Dostupno ažuriranje")
    msg.setText(f"Nova verzija <b>{new_version}</b> je dostupna.\n\nTrenutna verzija: {VERSION}")
    msg.setInformativeText("Želiš li ažurirati i restartati aplikaciju?")
    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    msg.setDefaultButton(QMessageBox.StandardButton.Yes)
    if msg.exec() != QMessageBox.StandardButton.Yes:
        return

    progress = QProgressDialog("Preuzimanje ažuriranja...", None, 0, 0)
    progress.setWindowTitle("Ažuriranje")
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.show()

    def _on_progress(pct):
        def _upd():
            if pct >= 0:
                if progress.maximum() == 0:
                    progress.setMaximum(100)
                progress.setValue(pct)
        QTimer.singleShot(0, _upd)

    def _done(ok):
        checker.download_done.disconnect(_done)
        progress.close()
        if ok:
            QMessageBox.information(None, "Ažuriranje završeno",
                                    "Ažuriranje je uspješno instalirano.\nAplikacija će se restartati.")
            from updater import restart_app
            restart_app()
        else:
            QMessageBox.warning(None, "Greška",
                                "Ažuriranje nije uspjelo. Pokušaj ručno preuzeti novu verziju.")

    checker.download_done.connect(_done)
    checker.download_in_background(_on_progress)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Tacx Neo 2T Controller")
    app.setOrganizationName("TacxApp")

    loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: (asyncio.set_event_loop(loop), loop.run_forever()),
                     daemon=True).start()

    import builtins
    builtins._asyncio_loop = loop

    from ui.main_window import MainWindow
    window = MainWindow()
    window.resize(1280, 720)
    window.show()

    # Update checker — drži referencu na app da _ask_update može dohvatiti checker
    app._update_checker = UpdateChecker()
    app._update_checker.update_available.connect(_ask_update)
    QTimer.singleShot(3000, app._update_checker.check_in_background)

    ret = app.exec()
    loop.call_soon_threadsafe(loop.stop)
    sys.exit(ret)


if __name__ == "__main__":
    main()
