from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    multiprocessing.freeze_support()

    from PyQt6.QtWidgets import QApplication

    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Craft Corner Label Maker")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
