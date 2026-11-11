"""Unit tests for PySide6 GUI components and modular tabs in offscreen mode."""

import os
import tempfile
import unittest
from pathlib import Path

# Force Qt offscreen platform before importing PySide6
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from config import PosterConfig
from gui.main_window import MainWindow
from storage import CampaignRepository, PostRepository


class TestGuiInitialization(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _create_isolated_window(self, tmpdir: str) -> MainWindow:
        tmp = Path(tmpdir)
        config = PosterConfig(
            db_path=tmp / "test_gui.db",
            history_file=tmp / "nonexistent_history.json",
        )
        return MainWindow(config)

    def test_main_window_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            win = self._create_isolated_window(tmpdir)
            try:
                win.resize(1050, 700)
                win.show()
                self.app.processEvents()
                self.assertIsNotNone(win)
                self.assertEqual(win.tabs.count(), 4)
                self.assertIsNotNone(win.menuBar())
                self.assertIsNotNone(win.tab_campaign.table_groups)
                self.assertIsNotNone(win.tab_history.table_history)
                self.assertEqual(win.tab_history.table_history.columnCount(), 6)
                self.assertIsNotNone(win.tab_campaigns_posts.table_campaigns)
                self.assertIsNotNone(win.tab_campaigns_posts.table_campaign_posts)
                self.assertIsNotNone(win.tab_campaign.btn_start)
                self.assertIsNotNone(win.tab_campaign.lbl_config_summary)
                self.assertLess(
                    win.tab_campaign.txt_content_preview.geometry().bottom(),
                    win.tab_campaign.lbl_media_summary.geometry().top(),
                )
            finally:
                win.close()
                self.app.processEvents()

    def test_config_summary_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            win = self._create_isolated_window(tmpdir)
            try:
                win.tab_config.chk_dry_run.setChecked(True)
                self.assertIn(
                    "Simulación (Dry-Run)",
                    win.tab_campaign.lbl_config_summary.text(),
                )
                win.tab_config.chk_dry_run.setChecked(False)
                self.assertIn(
                    "Publicación Real",
                    win.tab_campaign.lbl_config_summary.text(),
                )
            finally:
                win.close()
                self.app.processEvents()

    def test_group_selection_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            win = self._create_isolated_window(tmpdir)
            try:
                win.tab_campaign.set_all_groups_checked(False)
                self.assertEqual(len(win.tab_campaign.get_selected_group_urls()), 0)

                win.tab_campaign.set_all_groups_checked(True)
                selected = win.tab_campaign.get_selected_group_urls()
                self.assertEqual(len(selected), win.tab_campaign.table_groups.rowCount())
            finally:
                win.close()
                self.app.processEvents()

    def test_campaigns_and_posts_tab_populates_associated_posts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            win = self._create_isolated_window(tmpdir)
            try:
                camp_repo = CampaignRepository(win.db_manager)
                post_repo = PostRepository(win.db_manager)

                c1 = camp_repo.create_campaign(
                    name="Campaña Moto",
                    post_text="Texto de prueba",
                    bundle_dir="moto_electrica_uruz",
                    activate=True,
                )
                post_repo.record_post(
                    campaign_id=c1.id,
                    group_url="https://www.facebook.com/groups/111/",
                    status="SUCCESS",
                    post_url="https://www.facebook.com/groups/111/posts/999/",
                    fb_post_id="999",
                    details="OK",
                )
                post_repo.record_post(
                    campaign_id=c1.id,
                    group_url="https://www.facebook.com/groups/222/",
                    status="FAILED",
                    details="Timeout",
                )

                tab = win.tab_campaigns_posts
                tab.refresh()
                tab.table_campaigns.selectRow(0)
                self.app.processEvents()

                self.assertGreaterEqual(tab.table_campaigns.rowCount(), 1)
                self.assertEqual(tab.table_campaigns.item(0, 1).text(), "Campaña Moto")
                self.assertEqual(tab.table_campaigns.item(0, 3).text(), "1")
                self.assertEqual(tab.table_campaigns.item(0, 4).text(), "1")

                self.assertEqual(tab.table_campaign_posts.rowCount(), 1)
                self.assertEqual(
                    tab.table_campaign_posts.item(0, 2).text(),
                    "https://www.facebook.com/groups/111/posts/999/",
                )

                idx_all = tab.combo_campaign_post_filter.findData("ALL")
                tab.combo_campaign_post_filter.setCurrentIndex(idx_all)
                self.assertEqual(tab.table_campaign_posts.rowCount(), 2)
            finally:
                win.close()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
