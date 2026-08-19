"""Application entry point: ``python -m sss_aug_studio.app.main`` or ``sss-aug-studio``."""

from __future__ import annotations

import sys
from importlib import resources


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from ..gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("SSS Augmentation Studio")
    try:
        qss = (resources.files("sss_aug_studio.gui") / "style.qss").read_text(encoding="utf-8")
        app.setStyleSheet(qss)
    except (FileNotFoundError, OSError):
        pass
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:  # optional: dataset path on the command line
        win.explorer.open_dataset(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
