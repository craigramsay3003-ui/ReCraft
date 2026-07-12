"""Application entry point."""

import sys
from importlib.resources import as_file, files


def main() -> int:
    """Create and run the ReCraft desktop application."""
    from PySide6.QtWidgets import QApplication

    from recraft.ui.main_window import MainWindow

    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("ReCraft")
    from PySide6.QtGui import QIcon

    with as_file(files("recraft").joinpath("assets/recraft.ico")) as icon_path:
        application.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return application.exec()
