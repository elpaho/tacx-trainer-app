import sys
import os
import asyncio
import threading

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Tacx Neo 2T Controller")
    app.setOrganizationName("TacxApp")

    # Pokrenemo asyncio loop u zasebnom threadu
    # Qt UI ostaje u glavnom threadu
    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

    # Pohranimo loop globalno da ga main_window može koristiti
    import builtins
    builtins._asyncio_loop = loop

    window = MainWindow()
    window.resize(1280, 720)
    window.show()

    ret = app.exec()
    loop.call_soon_threadsafe(loop.stop)
    sys.exit(ret)


if __name__ == "__main__":
    main()
