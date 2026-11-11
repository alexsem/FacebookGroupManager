"""Unit tests for PySide6 GUI components in offscreen mode."""

import os
import unittest

# Force Qt offscreen platform before importing PySide6
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from config import PosterConfig
from gui.main_window import MainWindow


class TestGuiInitialization(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_creation(self) -> None:
        config = PosterConfig()
        win = MainWindow(config)
        try:
            self.assertIsNotNone(win)
            self.assertGreaterEqual(win.tabs.count(), 2)
            self.assertIsNotNone(win.table_groups)
            self.assertIsNotNone(win.btn_start)
        finally:
            win.close()
            self.app.processEvents()

    def test_group_selection_helpers(self) -> None:
        config = PosterConfig()
        win = MainWindow(config)
        try:
            win._set_all_groups_checked(False)
            self.assertEqual(len(win._get_selected_group_urls()), 0)

            win._set_all_groups_checked(True)
            selected = win._get_selected_group_urls()
            self.assertEqual(len(selected), win.table_groups.rowCount())
        finally:
            win.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
