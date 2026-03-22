"""
Media Manager — entry point.
Multi-library media metadata and organization tool.
"""

import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from modules.core.config_manager import GlobalConfig
from modules.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Media Manager')
    app.setOrganizationName('RLS')

    global_config = GlobalConfig()

    window = MainWindow(global_config)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
