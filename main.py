import sys
import os
import asyncio
import threading

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PyQt6.QtCore import QTimer, Qt
from version import VERSION


def check_and_update(app):
    """Provjeri update u zasebnom threadu, prikaži dialog u Qt threadu."""
    import threading
    from updater import check_for_update, download_and_install, restart_app

    def _check():
        new_version = check_for_update(VERSION)
        if not new_version:
            return
        # Prebaci na Qt thread
        QTimer.singleShot(0, lambda: _ask_update(new_version))

    def _ask_update(new_version):
        msg = QMessageBox()
        msg.setWindowTitle("Dostupno ažuriranje")
        msg.setText(f"Nova verzija <b>{new_version}</b> je dostupna.\n\nTrenutna verzija: {VERSION}")
        msg.setInformativeText("Želiš li ažurirati i restartati aplikaciju?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        # Progress dialog
        progress = QProgressDialog("Preuzimanje ažuriranja...", None, 0, 100)
        progress.setWindowTitle("Ažuriranje")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        def _on_progress(pct):
            QTimer.singleShot(0, lambda: progress.setValue(pct))

        def _download():
            ok = download_and_install(on_progress=_on_progress)
            QTimer.singleShot(0, lambda: _done(ok))

        def _done(ok):
            progress.close()
            if ok:
                QMessageBox.information(None, "Ažuriranje završeno",
                                        "Ažuriranje je uspješno. Aplikacija će se restartati.")
                restart_app()
            else:
                QMessageBox.warning(None, "Greška",
                                    "Ažuriranje nije uspjelo. Pokušaj ručno preuzeti novu verziju.")

        threading.Thread(target=_download, daemon=True).start()

    threading.Thread(target=_check, daemon=True).start()


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

    # Provjeri update 3 sekunde nakon pokretanja — ne blokira startup
    QTimer.singleShot(3000, lambda: check_and_update(app))

    ret = app.exec()
    loop.call_soon_threadsafe(loop.stop)
    sys.exit(ret)


if __name__ == "__main__":
    main()
