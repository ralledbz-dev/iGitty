import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from app import GitHubClient, MainWindow


class CommanderLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def populate(self):
        self.window.api = GitHubClient("sample-token")
        self.window.repositories = [
            {
                "name": "alpha",
                "owner": {"login": "demo"},
                "private": False,
                "description": "Public project",
                "updated_at": "2026-10-30T12:00:00Z",
            },
            {
                "name": "beta",
                "owner": {"login": "demo"},
                "private": True,
                "description": "Private project",
                "updated_at": "2026-10-01T12:00:00Z",
            },
        ]
        self.window.pages.setCurrentWidget(self.window.manager_page)
        self.window.render_repositories()

    def test_local_pane_is_available_without_github(self):
        self.assertEqual(self.window.splitter.count(), 2)
        self.assertIs(self.window.splitter.widget(1), self.window.local_pane)
        self.assertTrue(Path(self.window.local_pane.current_path()).is_dir())
        self.assertIs(self.window.pages.currentWidget(), self.window.login_page)
        self.assertFalse(self.window.zip_button.isEnabled())

    def test_repository_filters_preserve_selected_repository(self):
        self.populate()
        self.assertEqual(self.window.table.rowCount(), 2)
        self.window.visibility_filter.setCurrentIndex(2)
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertEqual(self.window.selected_repository()["name"], "beta")
        self.window.search_edit.setText("absent")
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertFalse(self.window.files_button.isEnabled())

    def test_download_dialog_starts_in_right_hand_folder(self):
        self.populate()
        with patch("app.QFileDialog.getSaveFileName", return_value=("", "")) as dialog:
            self.window.download_selected("zip")
        suggested = Path(dialog.call_args.args[2])
        self.assertEqual(suggested.parent, Path(self.window.local_pane.current_path()))
        self.assertEqual(suggested.name, "demo-alpha.zip")

    def test_disconnect_clears_online_selection_not_local_path(self):
        self.populate()
        local_path = self.window.local_pane.current_path()
        self.window.token_input.setText("temporary-test-token")
        self.window.disconnect()
        self.assertIsNone(self.window.api)
        self.assertEqual(self.window.token_input.text(), "")
        self.assertFalse(self.window.delete_button.isEnabled())
        self.assertEqual(self.window.local_pane.current_path(), local_path)
        self.assertIs(self.window.pages.currentWidget(), self.window.login_page)


if __name__ == "__main__":
    unittest.main()
