import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog

from gitea_dialog import GiteaMirrorDialog


_APP = QApplication.instance() or QApplication([])


class GiteaMirrorDialogTests(unittest.TestCase):
    def make_dialog(self, source=None, owner="authenticated"):
        dialog = GiteaMirrorDialog(
            None,
            source
            or {
                "owner": {"login": "github-owner"},
                "name": "source-repo",
                "private": False,
            },
            owner,
        )
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_defaults_show_source_and_use_private_target_without_token(self):
        dialog = self.make_dialog(owner=" authenticated ")

        self.assertEqual(dialog.owner_edit.text(), "authenticated")
        self.assertEqual(dialog.name_edit.text(), "source-repo")
        self.assertTrue(dialog.private_checkbox.isChecked())
        self.assertTrue(dialog.private_checkbox.isEnabled())
        self.assertFalse(dialog.token_checkbox.isChecked())
        self.assertEqual(
            dialog.values(),
            {
                "target_owner": "authenticated",
                "target_name": "source-repo",
                "private": True,
                "include_github_token": False,
            },
        )

    def test_private_source_forces_privacy_and_requires_token_consent(self):
        dialog = self.make_dialog(
            {
                "owner": {"login": "private-owner"},
                "name": "private-repo",
                "private": True,
            }
        )

        self.assertTrue(dialog.private_checkbox.isChecked())
        self.assertFalse(dialog.private_checkbox.isEnabled())
        self.assertFalse(dialog.token_checkbox.isChecked())

        with patch("gitea_dialog.QMessageBox.warning") as warning:
            self.assertFalse(dialog.validate_and_accept())
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)

        dialog.token_checkbox.setChecked(True)
        self.assertTrue(dialog.validate_and_accept())
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(dialog.values()["include_github_token"])

    def test_invalid_names_warn_and_do_not_accept(self):
        dialog = self.make_dialog()
        dialog.owner_edit.setText("bad/name")
        dialog.name_edit.setText("valid-name")

        with patch("gitea_dialog.QMessageBox.warning") as warning:
            self.assertFalse(dialog.validate_and_accept())

        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_valid_values_are_trimmed_before_acceptance(self):
        dialog = self.make_dialog()
        dialog.owner_edit.setText("  target-owner  ")
        dialog.name_edit.setText("  target-repo  ")

        self.assertTrue(dialog.validate_and_accept())
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.values()["target_owner"], "target-owner")
        self.assertEqual(dialog.values()["target_name"], "target-repo")


if __name__ == "__main__":
    unittest.main()
