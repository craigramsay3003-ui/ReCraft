"""Application entry point."""

import sys


def main() -> int:
    """Create and run the ReCraft desktop application."""
    from PySide6.QtWidgets import QApplication

    from recraft.ui.main_window import MainWindow

    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("ReCraft")
    window = MainWindow()
    window.show()
    return application.exec()
