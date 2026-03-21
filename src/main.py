import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui import MainWindow

_BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(_BASE_DIR / "images" / "pdfbook.ico")))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
