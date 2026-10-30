import tempfile
import unittest
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from local_panel import LocalFilesPane

_APP = QApplication.instance() or QApplication([])


class LocalFilesPaneTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        (self.root / "folder").mkdir()
        (self.root / "folder" / "note.txt").write_text("hello", encoding="utf-8")
        (self.root / "root.txt").write_text("root", encoding="utf-8")
        self.pane = LocalFilesPane()
        self.addCleanup(self.pane.deleteLater)
        self.assertTrue(self.pane._set_path(str(self.root)))
        QTest.qWait(100)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_current_path_is_resolved_and_directory_is_listed(self):
        self.assertEqual(self.pane.current_path(), str(self.root))
        self.assertEqual(self.pane.path_edit.text(), str(self.root))
        self.assertGreaterEqual(
            self.pane.model.rowCount(self.pane.files_view.rootIndex()), 2
        )

    def test_open_selected_directory_navigates_and_go_up_returns(self):
        folder_index = self.pane.model.index(str(self.root / "folder"))
        self.pane.files_view.setCurrentIndex(folder_index)
        self.assertEqual(self.pane.selected_path(), str(self.root / "folder"))
        self.pane.open_selected()
        self.assertEqual(self.pane.current_path(), str(self.root / "folder"))
        self.pane.go_up()
        self.assertEqual(self.pane.current_path(), str(self.root))

    def test_selection_path_for_file_is_available(self):
        file_index = self.pane.model.index(str(self.root / "root.txt"))
        self.pane.files_view.setCurrentIndex(file_index)
        self.assertEqual(self.pane.selected_path(), str(self.root / "root.txt"))

    def test_nonexistent_navigation_keeps_current_path(self):
        before = self.pane.current_path()
        self.pane.path_edit.setText(str(self.root / "does-not-exist"))
        self.pane.path_edit.returnPressed.emit()
        self.assertEqual(self.pane.current_path(), before)

    def test_refresh_and_navigation_do_not_delete_anything(self):
        self.pane.refresh()
        self.pane.go_up()
        self.assertTrue((self.root / "folder" / "note.txt").exists())
        self.assertTrue((self.root / "root.txt").exists())
        self.assertTrue((self.root / "folder").is_dir())

    def test_no_destructive_file_operations_are_exposed(self):
        # Check the pane's own public API, not inherited QWidget lifecycle and
        # pointer-event methods such as moveEvent() or deleteLater().
        public_names = set(LocalFilesPane.__dict__)
        for forbidden in ("delete", "move", "copy", "rename"):
            self.assertFalse(any(forbidden in name.lower() for name in public_names))


if __name__ == "__main__":
    unittest.main()
