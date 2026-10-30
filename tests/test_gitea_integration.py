import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QDialog

from app import GitHubClient, MainWindow
from gitea_client import GiteaError


class GiteaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.repo = {
            "owner": {"login": "github-owner"},
            "name": "demo",
            "full_name": "github-owner/demo",
            "private": False,
        }
        self.client = Mock()
        self.client.get_user.return_value = {"login": "ralf"}
        self.client.create_mirror.return_value = {"name": "demo", "mirror": True}

        def run_synchronously(fn, on_success, on_error=None, message=""):
            try:
                result = fn()
            except Exception as error:
                if on_error is None:
                    raise
                on_error(error)
            else:
                on_success(result)

        self.window.run_task = Mock(side_effect=run_synchronously)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def populate(self):
        self.window.api = GitHubClient("github-test-token")
        self.window.repositories = [self.repo]
        self.window.render_repositories()

    def options(self, include_token=False):
        return {
            "target_owner": "ralf",
            "target_name": "demo",
            "private": True,
            "include_github_token": include_token,
        }

    def test_mirror_requires_github_selection(self):
        self.assertFalse(self.window.mirror_button.isEnabled())
        self.assertFalse(self.window.mirror_action.isEnabled())
        self.populate()
        self.assertTrue(self.window.mirror_button.isEnabled())
        self.window.disconnect()
        self.assertFalse(self.window.mirror_button.isEnabled())

    @patch("app.QMessageBox.warning")
    @patch(
        "app.GiteaClient.from_environment",
        side_effect=GiteaError("DBZS_HOME_API_TOKEN fehlt"),
    )
    def test_missing_environment_token_does_not_start_task(self, factory, warning):
        self.populate()
        self.window.mirror_selected()
        warning.assert_called_once()
        self.window.run_task.assert_not_called()
        self.assertFalse(self.window._gitea_busy)

    @patch("app.GiteaMirrorDialog")
    @patch("app.GiteaClient.from_environment")
    def test_cancel_never_creates_mirror(self, factory, dialog):
        self.populate()
        factory.return_value = self.client
        dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
        self.window.mirror_selected()
        self.client.create_mirror.assert_not_called()
        self.assertFalse(self.window._gitea_busy)
        self.assertTrue(self.window.mirror_button.isEnabled())

    @patch("app.QMessageBox.information")
    @patch("app.GiteaMirrorDialog")
    @patch("app.GiteaClient.from_environment")
    def test_public_mirror_does_not_transfer_github_token_by_default(
        self, factory, dialog, information
    ):
        self.populate()
        factory.return_value = self.client
        dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
        dialog.return_value.values.return_value = self.options()
        with patch.object(self.window.api, "token_for_mirror") as token:
            self.window.mirror_selected()
            token.assert_not_called()
        self.client.create_mirror.assert_called_once_with(
            self.repo, "ralf", "demo", private=True, github_token=None
        )
        self.assertFalse(self.window._gitea_busy)
        information.assert_called_once()

    @patch("app.QMessageBox.information")
    @patch("app.GiteaMirrorDialog")
    @patch("app.GiteaClient.from_environment")
    def test_explicit_token_consent_is_respected(self, factory, dialog, information):
        self.populate()
        factory.return_value = self.client
        dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
        dialog.return_value.values.return_value = self.options(include_token=True)
        self.window.mirror_selected()
        self.client.create_mirror.assert_called_once_with(
            self.repo, "ralf", "demo", private=True, github_token="github-test-token"
        )
        self.assertTrue(self.window.mirror_button.isEnabled())

    @patch("app.GiteaClient.from_environment")
    def test_busy_operation_is_not_repeated(self, factory):
        self.populate()
        self.window.set_gitea_busy(True)
        self.assertFalse(self.window.mirror_button.isEnabled())
        self.window.mirror_selected()
        factory.assert_not_called()

    @patch("app.QMessageBox.critical")
    @patch("app.GiteaClient.from_environment")
    def test_failed_connection_restores_actions(self, factory, critical):
        self.populate()
        factory.return_value = self.client
        self.client.get_user.side_effect = GiteaError("Verbindung fehlgeschlagen")
        self.window.mirror_selected()
        self.client.create_mirror.assert_not_called()
        self.assertFalse(self.window._gitea_busy)
        self.assertTrue(self.window.mirror_button.isEnabled())
        critical.assert_called_once()

    @patch("app.QMessageBox.information")
    @patch("app.GiteaClient.from_environment")
    def test_connection_check_works_without_github(self, factory, information):
        factory.return_value = self.client
        self.window.check_gitea_connection()
        self.client.get_user.assert_called_once_with()
        self.assertFalse(self.window._gitea_busy)
        information.assert_called_once()


if __name__ == "__main__":
    unittest.main()
