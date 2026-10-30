from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "iGitty"
API_ROOT = "https://api.github.com"
MAX_FILE_BYTES = 1024 * 1024


class GitHubError(RuntimeError):
    """A safe, user-facing error returned by GitHub or a local operation."""


def validate_repo_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name or "") or name in {".", ".."}:
        raise ValueError(
            "Der Repository-Name darf nur Buchstaben, Zahlen, Punkt, Bindestrich und Unterstrich enthalten."
        )
    return name


def validate_file_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 1024
        or value.startswith("/")
    ):
        raise ValueError("Bitte einen gültigen relativen Dateipfad angeben.")
    parts = value.split("/")
    if any(not part or part in {".", ".."} or "\\" in part for part in parts):
        raise ValueError("Der Dateipfad ist ungültig.")
    return value


def format_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))  # noqa: FURB162
        return parsed.astimezone().strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return "—"


class GitHubClient:
    """Small GitHub REST client. The token is kept only on this object in memory."""

    def __init__(self, token: str):
        self._token = token.strip()
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "iGitty-PySide6-local-repository-manager",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        payload: dict | None = None,
        timeout: tuple[int, int] = (12, 60),
    ) -> Any:
        try:
            response = requests.request(
                method,
                f"{API_ROOT}{path}",
                headers=self._headers,
                params=params,
                json=payload,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            raise GitHubError(
                "GitHub antwortet nicht rechtzeitig. Bitte prüfe deine Internetverbindung."
            ) from exc
        except requests.RequestException as exc:
            raise GitHubError(
                "GitHub konnte nicht erreicht werden. Bitte prüfe deine Internetverbindung."
            ) from exc

        if not response.ok:
            try:
                detail = response.json().get("message", "")
            except (ValueError, AttributeError):
                detail = ""
            if response.status_code == 401:
                detail = "Der Token wurde abgelehnt. Prüfe den Token und seine Berechtigungen."
            elif response.status_code == 403:
                detail = (
                    detail
                    or "GitHub hat den Zugriff verweigert. Prüfe Token-Berechtigungen oder API-Limits."
                )
            elif response.status_code == 404:
                detail = (
                    detail
                    or "Repository oder Datei nicht gefunden; eventuell fehlen Zugriffsrechte."
                )
            raise GitHubError(detail or f"GitHub meldet HTTP {response.status_code}.")

        if response.status_code == 204 or not response.content:
            return None
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return response.json()
        return response.content

    def get_user(self) -> dict:
        user = self.request("GET", "/user")
        if not isinstance(user, dict) or not user.get("login"):
            raise GitHubError("GitHub hat kein gültiges Benutzerprofil zurückgegeben.")
        return user

    def list_repositories(self) -> list[dict]:
        path = "/user/repos"
        params = {
            "affiliation": "owner,collaborator,organization_member",
            "sort": "updated",
            "per_page": 100,
            "page": 1,
        }
        repositories: list[dict] = []
        while params["page"] <= 20:
            try:
                response = requests.get(
                    f"{API_ROOT}{path}",
                    headers=self._headers,
                    params=params,
                    timeout=(12, 60),
                )
            except requests.RequestException as exc:
                raise GitHubError(
                    "Die Repository-Liste konnte nicht geladen werden."
                ) from exc
            if not response.ok:
                try:
                    detail = response.json().get("message", "")
                except (ValueError, AttributeError):
                    detail = ""
                raise GitHubError(
                    detail or f"GitHub meldet HTTP {response.status_code}."
                )
            page = response.json()
            if not isinstance(page, list):
                raise GitHubError(
                    "GitHub hat keine gültige Repository-Liste geliefert."
                )
            repositories.extend(page)
            if not response.links.get("next"):
                break
            params["page"] += 1
        return repositories

    @staticmethod
    def repo_path(owner: str, repo: str) -> str:
        return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"

    def update_repository(self, owner: str, repo: str, changes: dict) -> dict:
        return self.request("PATCH", self.repo_path(owner, repo), payload=changes)

    def delete_repository(self, owner: str, repo: str) -> None:
        self.request("DELETE", self.repo_path(owner, repo))

    def get_contents(self, owner: str, repo: str, path: str = "", ref: str = "") -> Any:
        params: dict[str, str] = {}
        if path:
            params["path"] = validate_file_path(path)
        if ref:
            params["ref"] = ref
        data = self.request(
            "GET", f"{self.repo_path(owner, repo)}/contents", params=params
        )
        if isinstance(data, dict) and data.get("type") == "file":
            if data.get("size", 0) > MAX_FILE_BYTES or data.get("encoding") != "base64":
                raise GitHubError(
                    "Diese Datei ist zu groß oder nicht als Textdatei bearbeitbar (maximal 1 MB)."
                )
            try:
                data["text_content"] = base64.b64decode(
                    data.get("content", ""), validate=False
                ).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitHubError(
                    "Die Datei ist keine lesbare UTF-8-Textdatei."
                ) from exc
        return data

    def save_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> dict:
        validate_file_path(path)
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise ValueError("Dateien dürfen höchstens 1 MB groß sein.")
        if not message.strip() or len(message) > 200:
            raise ValueError(
                "Bitte eine Commit-Nachricht mit höchstens 200 Zeichen eingeben."
            )
        payload: dict[str, Any] = {
            "message": message.strip(),
            "content": base64.b64encode(encoded).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
        return self.request(
            "PUT",
            f"{self.repo_path(owner, repo)}/contents/{encoded_path}",
            payload=payload,
        )

    def download_archive(self, owner: str, repo: str, destination: str) -> None:
        url = f"{API_ROOT}{self.repo_path(owner, repo)}/zipball"
        try:
            with requests.get(
                url, headers=self._headers, stream=True, timeout=(15, 180)
            ) as response:
                if not response.ok:
                    raise GitHubError(
                        f"Das ZIP-Archiv konnte nicht geladen werden (HTTP {response.status_code})."
                    )
                with open(destination, "wb") as output:
                    for chunk in response.iter_content(chunk_size=128 * 1024):
                        if chunk:
                            output.write(chunk)
        except requests.Timeout as exc:
            raise GitHubError("Der ZIP-Download hat zu lange gedauert.") from exc
        except requests.RequestException as exc:
            raise GitHubError("Das ZIP-Archiv konnte nicht geladen werden.") from exc

    def create_git_bundle(self, owner: str, repo: str, destination: str) -> None:
        if not shutil.which("git"):
            raise GitHubError(
                "Für vollständige Git-Backups muss Git installiert und im PATH verfügbar sein."
            )
        # Git receives authorization through a temporary process environment only.
        # It is not written to the repository URL, Git config, or the bundle.
        authorization = base64.b64encode(
            f"x-access-token:{self._token}".encode()
        ).decode("ascii")
        env = os.environ.copy()
        env.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {authorization}",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        with tempfile.TemporaryDirectory(prefix="ig-bundle-") as temp_dir:
            mirror = str(Path(temp_dir) / "mirror.git")
            clone = subprocess.run(
                [
                    "git",
                    "clone",
                    "--mirror",
                    "--quiet",
                    "--",
                    f"https://github.com/{owner}/{repo}.git",
                    mirror,
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if clone.returncode:
                raise GitHubError(
                    "Git konnte das Repository nicht spiegeln. Prüfe Git-Installation, Verbindung und Zugriffsrechte."
                )
            bundle = subprocess.run(
                ["git", "-C", mirror, "bundle", "create", destination, "--all"],
                check=False,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if bundle.returncode:
                raise GitHubError("Das Git-Bundle konnte nicht erstellt werden.")


class WorkerSignals(QObject):
    done = Signal(object, object)


class Worker(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(self.fn(), None)
        except Exception as exc:  # noqa: BLE001  # Forward task failures to the GUI thread.
            self.signals.done.emit(None, exc)


class RepoFilesDialog(QDialog):
    def __init__(self, parent: MainWindow, repo: dict):
        super().__init__(parent)
        self.manager = parent
        self.repo = repo
        self.current_path = ""
        self.setWindowTitle(f"Dateien · {repo['full_name']}")
        self.setMinimumSize(690, 510)
        layout = QVBoxLayout(self)

        heading = QLabel(repo["full_name"])
        heading.setObjectName("dialogTitle")
        layout.addWidget(heading)
        self.path_label = QLabel(
            "/ · Standard-Branch: " + (repo.get("default_branch") or "main")
        )
        self.path_label.setObjectName("muted")
        layout.addWidget(self.path_label)

        controls = QHBoxLayout()
        self.up_button = QPushButton("← Übergeordneter Ordner")
        self.up_button.clicked.connect(self.go_up)
        self.new_button = QPushButton("＋ Neue Textdatei")
        self.new_button.setObjectName("primaryButton")
        self.new_button.clicked.connect(lambda: self.edit_file(None))
        controls.addWidget(self.up_button)
        controls.addStretch(1)
        controls.addWidget(self.new_button)
        layout.addLayout(controls)

        self.file_list = QListWidget()
        self.file_list.itemActivated.connect(self.open_item)
        layout.addWidget(self.file_list, 1)
        hint = QLabel(
            "Textdateien bis 1 MB lassen sich bearbeiten. Speichern erstellt einen Commit im Standard-Branch."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.load_path("")

    def load_path(self, path: str) -> None:
        self.current_path = path
        branch = self.repo.get("default_branch") or "main"
        self.path_label.setText(
            f"/{path}  ·  Branch: {branch}" if path else f"/  ·  Branch: {branch}"
        )
        self.up_button.setEnabled(bool(path))
        self.file_list.clear()
        loading = QListWidgetItem("Lade Dateien …")
        loading.setFlags(Qt.ItemFlag.NoItemFlags)
        self.file_list.addItem(loading)
        self.manager.run_task(
            lambda: self.manager.api.get_contents(
                self.repo["owner"]["login"], self.repo["name"], path, branch
            ),
            self.show_items,
            lambda error: self.show_error(error),
            "Lade Dateien …",
        )

    def show_items(self, items: Any) -> None:
        self.file_list.clear()
        if not isinstance(items, list):
            self.file_list.addItem("Dieser Pfad enthält keine Ordnerliste.")
            return
        items = sorted(
            items,
            key=lambda item: (
                item.get("type") != "dir",
                item.get("name", "").casefold(),
            ),
        )
        if not items:
            self.file_list.addItem("Dieser Ordner ist leer.")
            return
        for entry in items:
            is_dir = entry.get("type") == "dir"
            size = entry.get("size", 0) or 0
            size_label = (
                "Ordner"
                if is_dir
                else (f"{size / 1024:.0f} KB" if size >= 1024 else f"{size} B")
            )
            item = QListWidgetItem(
                f"{'▰' if is_dir else '▤'}   {entry.get('name', '')}   ·   {size_label}"
            )
            item.setData(Qt.ItemDataRole.UserRole, (entry.get("path", ""), is_dir))
            self.file_list.addItem(item)

    def show_error(self, error: Exception) -> None:
        self.file_list.clear()
        self.file_list.addItem(str(error))

    def open_item(self, item: QListWidgetItem) -> None:
        details = item.data(Qt.ItemDataRole.UserRole)
        if not details:
            return
        path, is_dir = details
        if is_dir:
            self.load_path(path)
        else:
            self.load_file(path)

    def go_up(self) -> None:
        if self.current_path:
            self.load_path("/".join(self.current_path.split("/")[:-1]))

    def load_file(self, path: str) -> None:
        branch = self.repo.get("default_branch") or "main"
        self.manager.run_task(
            lambda: self.manager.api.get_contents(
                self.repo["owner"]["login"], self.repo["name"], path, branch
            ),
            lambda data: self.show_editor(path, data),
            lambda error: QMessageBox.critical(
                self, "Datei konnte nicht geöffnet werden", str(error)
            ),
            "Lade Datei …",
        )

    def show_editor(self, path: str | None, data: dict | None = None) -> None:
        dialog = FileEditorDialog(self, path, data or {})
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            self.manager.run_task(
                lambda: self.manager.api.save_file(
                    self.repo["owner"]["login"],
                    self.repo["name"],
                    values["path"],
                    values["content"],
                    values["message"],
                    self.repo.get("default_branch") or "main",
                    values["sha"],
                ),
                lambda _result: self.after_save(values["path"]),
                lambda error: QMessageBox.critical(
                    self, "Speichern fehlgeschlagen", str(error)
                ),
                "Commit wird erstellt …",
            )

    def after_save(self, path: str) -> None:
        QMessageBox.information(
            self, "Gespeichert", f"Der Commit für „{path}“ wurde bei GitHub erstellt."
        )
        self.load_path(self.current_path)


class FileEditorDialog(QDialog):
    def __init__(self, parent: RepoFilesDialog, path: str | None, data: dict):
        super().__init__(parent)
        self.existing = bool(path)
        self.file_sha = data.get("sha")
        self.setWindowTitle("Datei bearbeiten" if path else "Neue Textdatei")
        self.setMinimumWidth(700)
        self.resize(780, 650)
        layout = QVBoxLayout(self)
        title = QLabel("Datei bearbeiten" if path else "Neue Textdatei")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        form = QFormLayout()
        self.path_edit = QLineEdit(
            path or (f"{parent.current_path}/" if parent.current_path else "")
        )
        self.path_edit.setPlaceholderText("ordner/datei.txt")
        self.path_edit.setReadOnly(self.existing)
        form.addRow("Dateipfad", self.path_edit)
        layout.addLayout(form)
        layout.addWidget(QLabel("Inhalt"))
        self.content = QPlainTextEdit()
        self.content.setObjectName("codeEditor")
        self.content.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.content.setPlainText(data.get("text_content", ""))
        layout.addWidget(self.content, 1)
        form2 = QFormLayout()
        self.message = QLineEdit(
            f"Datei {Path(path).name} aktualisiert"
            if path
            else "Datei über iGitty hinzugefügt"
        )
        self.message.setMaxLength(200)
        form2.addRow("Commit-Nachricht", self.message)
        layout.addLayout(form2)
        note = QLabel(
            "Der Commit wird direkt im Standard-Branch erstellt. Maximale Dateigröße: 1 MB."
        )
        note.setObjectName("muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Commit speichern")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName(
            "primaryButton"
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self) -> None:
        try:
            validate_file_path(self.path_edit.text().strip())
            if len(self.content.toPlainText().encode("utf-8")) > MAX_FILE_BYTES:
                raise ValueError("Dateien dürfen höchstens 1 MB groß sein.")
            if not self.message.text().strip():
                raise ValueError("Bitte eine Commit-Nachricht eingeben.")
        except ValueError as exc:
            QMessageBox.warning(self, "Eingabe prüfen", str(exc))
            return
        self.accept()

    def values(self) -> dict:
        return {
            "path": self.path_edit.text().strip(),
            "content": self.content.toPlainText(),
            "message": self.message.text().strip(),
            "sha": self.file_sha,
        }


class MetadataDialog(QDialog):
    def __init__(self, parent: QWidget, repo: dict):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Repository-Details bearbeiten")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        title = QLabel("Repository-Details")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        form = QFormLayout()
        self.name = QLineEdit(repo.get("name", ""))
        self.name.setMaxLength(100)
        self.description = QPlainTextEdit(repo.get("description") or "")
        self.description.setMaximumHeight(95)
        self.homepage = QLineEdit(repo.get("homepage") or "")
        self.homepage.setMaxLength(255)
        self.private = QCheckBox("Privates Repository")
        self.private.setChecked(bool(repo.get("private")))
        form.addRow("Repository-Name", self.name)
        form.addRow("Beschreibung", self.description)
        form.addRow("Website", self.homepage)
        form.addRow("Sichtbarkeit", self.private)
        layout.addLayout(form)
        note = QLabel("Änderungen werden direkt bei GitHub gespeichert.")
        note.setObjectName("muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Änderungen speichern"
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName(
            "primaryButton"
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self) -> None:
        try:
            validate_repo_name(self.name.text().strip())
            if len(self.description.toPlainText()) > 350:
                raise ValueError(
                    "Die Beschreibung darf höchstens 350 Zeichen lang sein."
                )
            if len(self.homepage.text().strip()) > 255:
                raise ValueError(
                    "Die Website-Adresse darf höchstens 255 Zeichen lang sein."
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Eingabe prüfen", str(exc))
            return
        self.accept()

    def changes(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "description": self.description.toPlainText(),
            "homepage": self.homepage.text().strip(),
            "private": self.private.isChecked(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — GitHub Repository Manager")
        self.resize(1180, 780)
        self.setMinimumSize(900, 620)
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(4)
        self._workers: set[Worker] = set()
        self.api: GitHubClient | None = None
        self.repositories: list[dict] = []
        self.filtered_repositories: list[dict] = []
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            "Bereit · Deine Zugangsdaten werden nicht gespeichert"
        )
        self.build_ui()

    def build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(30, 20, 30, 22)
        root_layout.setSpacing(18)
        header = QHBoxLayout()
        brand = QLabel("iGitty")
        brand.setObjectName("brand")
        subtitle = QLabel("GITHUB REPOSITORY MANAGER")
        subtitle.setObjectName("brandSub")
        brand_box = QVBoxLayout()
        brand_box.setSpacing(0)
        brand_box.addWidget(brand)
        brand_box.addWidget(subtitle)
        header.addLayout(brand_box)
        header.addStretch(1)
        self.connection_label = QLabel("Nicht verbunden")
        self.connection_label.setObjectName("connectionState")
        header.addWidget(self.connection_label)
        self.disconnect_button = QPushButton("Trennen")
        self.disconnect_button.clicked.connect(self.disconnect)
        self.disconnect_button.hide()
        header.addWidget(self.disconnect_button)
        root_layout.addLayout(header)

        self.pages = QStackedWidget()
        self.login_page = self.build_login_page()
        self.manager_page = self.build_manager_page()
        self.pages.addWidget(self.login_page)
        self.pages.addWidget(self.manager_page)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

    def build_login_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(36, 42, 36, 42)
        layout.setSpacing(54)
        intro = QVBoxLayout()
        intro.addStretch(1)
        eyebrow = QLabel("DEIN GITHUB. ÜBERSICHTLICH.")
        eyebrow.setObjectName("eyebrow")
        intro.addWidget(eyebrow)
        heading = QLabel("Alle Repositories.\nEin klarer Überblick.")
        heading.setObjectName("heroTitle")
        intro.addWidget(heading)
        lead = QLabel(
            "Verwalte deine GitHub-Projekte an einem Ort: Dateien bearbeiten, Archive herunterladen und vollständige Git-Backups erstellen."
        )
        lead.setObjectName("heroLead")
        lead.setWordWrap(True)
        intro.addWidget(lead)
        intro.addSpacing(16)
        features = QLabel(
            "↓  ZIP-Download       ↗  Dateien bearbeiten       ◈  Git-Backups"
        )
        features.setObjectName("featureStrip")
        intro.addWidget(features)
        intro.addStretch(1)
        layout.addLayout(intro, 6)

        card = QFrame()
        card.setObjectName("connectCard")
        card.setMinimumWidth(370)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 26)
        card_layout.setSpacing(12)
        cap = QLabel("VERBINDUNG")
        cap.setObjectName("eyebrow")
        card_layout.addWidget(cap)
        title = QLabel("Mit GitHub verbinden")
        title.setObjectName("sectionTitle")
        card_layout.addWidget(title)
        body = QLabel(
            "Dein Personal Access Token wird nur im Arbeitsspeicher gehalten und beim Trennen oder Beenden verworfen."
        )
        body.setObjectName("muted")
        body.setWordWrap(True)
        card_layout.addWidget(body)
        card_layout.addSpacing(5)
        card_layout.addWidget(QLabel("GitHub Personal Access Token"))
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("github_pat_…")
        self.token_input.setClearButtonEnabled(True)
        self.token_input.returnPressed.connect(self.connect_github)
        card_layout.addWidget(self.token_input)
        self.connect_button = QPushButton("Sicher verbinden   →")
        self.connect_button.setObjectName("primaryButton")
        self.connect_button.clicked.connect(self.connect_github)
        card_layout.addWidget(self.connect_button)
        self.token_error = QLabel("")
        self.token_error.setObjectName("errorLabel")
        self.token_error.setWordWrap(True)
        self.token_error.hide()
        card_layout.addWidget(self.token_error)
        help_link = QPushButton("Token bei GitHub erstellen ↗")
        help_link.setObjectName("linkButton")
        help_link.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/settings/personal-access-tokens/new")
            )
        )
        card_layout.addWidget(help_link, alignment=Qt.AlignmentFlag.AlignLeft)
        permissions = QLabel(
            "Empfohlen: Fine-grained Token, beschränkt auf die gewünschten Repositories. Benötigt: Contents (Read and write) und Administration (Read and write)."
        )
        permissions.setObjectName("smallNote")
        permissions.setWordWrap(True)
        card_layout.addWidget(permissions)
        security = QLabel(
            "●  Läuft lokal auf diesem Computer · Token wird nicht gespeichert"
        )
        security.setObjectName("securityNote")
        security.setWordWrap(True)
        card_layout.addWidget(security)
        card_layout.addStretch(1)
        layout.addWidget(card, 4, alignment=Qt.AlignmentFlag.AlignVCenter)
        return page

    def build_manager_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 6, 12, 0)
        layout.setSpacing(16)
        intro = QHBoxLayout()
        text = QVBoxLayout()
        eyebrow = QLabel("REPOSITORY-BIBLIOTHEK")
        eyebrow.setObjectName("eyebrow")
        text.addWidget(eyebrow)
        title = QLabel("Deine Projekte.")
        title.setObjectName("pageTitle")
        text.addWidget(title)
        self.welcome_label = QLabel("")
        self.welcome_label.setObjectName("muted")
        text.addWidget(self.welcome_label)
        intro.addLayout(text)
        intro.addStretch(1)
        layout.addLayout(intro)

        stats = QHBoxLayout()
        self.stat_total = self.make_stat(stats, "REPOSITORIES")
        self.stat_public = self.make_stat(stats, "ÖFFENTLICH")
        self.stat_private = self.make_stat(stats, "PRIVAT")
        self.stat_recent = self.make_stat(stats, "LETZTE 30 TAGE")
        layout.addLayout(stats)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("⌕   Nach Repository suchen …")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.render_repositories)
        self.visibility_filter = QComboBox()
        self.visibility_filter.addItem("Alle Repositories", "all")
        self.visibility_filter.addItem("Öffentlich", "public")
        self.visibility_filter.addItem("Privat", "private")
        self.visibility_filter.currentIndexChanged.connect(self.render_repositories)
        self.refresh_button = QPushButton("⟳  Aktualisieren")
        self.refresh_button.clicked.connect(
            lambda: self.load_repositories(show_message=True)
        )
        toolbar.addWidget(self.search_edit, 1)
        toolbar.addWidget(self.visibility_filter)
        toolbar.addWidget(self.refresh_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                "Repository",
                "Beschreibung",
                "Sichtbarkeit",
                "Sprache",
                "★",
                "Aktualisiert",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        for column in (2, 3, 4, 5):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.itemSelectionChanged.connect(self.update_action_state)
        self.table.cellDoubleClicked.connect(
            lambda _row, _col: self.open_repository_url()
        )
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel(
            "Noch keine passenden Repositories. Ändere den Suchbegriff oder den Sichtbarkeitsfilter."
        )
        self.empty_label.setObjectName("muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide()
        layout.addWidget(self.empty_label, 1)

        actions = QHBoxLayout()
        self.files_button = self.action_button("Dateien bearbeiten", self.open_files)
        self.details_button = self.action_button("Details", self.edit_metadata)
        self.zip_button = self.action_button(
            "ZIP herunterladen ↓", lambda: self.download_selected("zip")
        )
        self.backup_button = self.action_button(
            "Git-Backup ◈", lambda: self.download_selected("bundle")
        )
        self.delete_button = self.action_button(
            "Repository löschen", self.delete_selected, danger=True
        )
        for button in (
            self.files_button,
            self.details_button,
            self.zip_button,
            self.backup_button,
            self.delete_button,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)
        for button in (
            self.files_button,
            self.details_button,
            self.zip_button,
            self.backup_button,
            self.delete_button,
        ):
            button.setEnabled(False)
        return page

    def make_stat(self, layout: QHBoxLayout, label: str) -> QLabel:
        card = QFrame()
        card.setObjectName("statCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 12, 16, 12)
        caption = QLabel(label)
        caption.setObjectName("statCaption")
        value = QLabel("—")
        value.setObjectName("statValue")
        box.addWidget(caption)
        box.addWidget(value)
        layout.addWidget(card, 1)
        return value

    def action_button(
        self, text: str, slot: Callable, danger: bool = False
    ) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("dangerButton" if danger else "secondaryButton")
        button.clicked.connect(slot)
        return button

    def run_task(
        self,
        fn: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None] | None = None,
        message: str = "Wird verarbeitet …",
    ) -> None:
        worker = Worker(fn)
        self._workers.add(worker)

        def finished(result: Any, error: Exception | None) -> None:
            self._workers.discard(worker)
            self.statusBar().showMessage("Bereit", 5000)
            if error:
                if on_error:
                    on_error(error)
                else:
                    QMessageBox.critical(self, "Fehler", str(error))
            else:
                on_success(result)

        worker.signals.done.connect(finished)
        self.statusBar().showMessage(message)
        self.pool.start(worker)

    def connect_github(self) -> None:
        token = self.token_input.text().strip()
        if len(token) < 10:
            self.token_error.setText(
                "Bitte einen gültigen GitHub Personal Access Token eingeben."
            )
            self.token_error.show()
            return
        self.token_error.hide()
        self.connect_button.setEnabled(False)
        self.connect_button.setText("Verbinde …")
        candidate = GitHubClient(token)

        def connected(user: dict) -> None:
            self.api = candidate
            self.token_input.clear()
            self.connection_label.setText(f"Verbunden als  {user['login']}")
            self.connection_label.setObjectName("connectedState")
            self.connection_label.style().unpolish(self.connection_label)
            self.connection_label.style().polish(self.connection_label)
            self.welcome_label.setText(
                f"Angemeldet als @{user['login']} · wähle ein Projekt, um loszulegen."
            )
            self.disconnect_button.show()
            self.pages.setCurrentWidget(self.manager_page)
            self.load_repositories()

        def failed(error: Exception) -> None:
            self.token_error.setText(str(error))
            self.token_error.show()
            self.connect_button.setEnabled(True)
            self.connect_button.setText("Sicher verbinden   →")

        def validate() -> dict:
            user = candidate.get_user()
            return user

        worker = Worker(validate)
        self._workers.add(worker)

        def finished(result: Any, error: Exception | None) -> None:
            self._workers.discard(worker)
            self.statusBar().showMessage("Bereit", 5000)
            self.connect_button.setEnabled(True)
            self.connect_button.setText("Sicher verbinden   →")
            if error:
                failed(error)
            else:
                connected(result)

        worker.signals.done.connect(finished)
        self.statusBar().showMessage("Prüfe Verbindung zu GitHub …")
        self.pool.start(worker)

    def disconnect(self) -> None:
        self.api = None
        self.repositories.clear()
        self.filtered_repositories.clear()
        self.table.setRowCount(0)
        self.connection_label.setText("Nicht verbunden")
        self.connection_label.setObjectName("connectionState")
        self.connection_label.style().unpolish(self.connection_label)
        self.connection_label.style().polish(self.connection_label)
        self.disconnect_button.hide()
        self.pages.setCurrentWidget(self.login_page)
        self.token_input.clear()
        self.statusBar().showMessage(
            "Getrennt · Zugangsdaten wurden aus dem Arbeitsspeicher verworfen", 6000
        )

    def load_repositories(self, show_message: bool = False) -> None:
        if not self.api:
            return

        def loaded(repos: list[dict]) -> None:
            self.repositories = repos
            self.render_repositories()
            if show_message:
                self.statusBar().showMessage(
                    f"{len(repos)} Repositories geladen.", 5000
                )

        client = self.api
        self.run_task(
            client.list_repositories, loaded, message="Lade Repositories von GitHub …"
        )

    def render_repositories(self, *_args: Any) -> None:
        search = self.search_edit.text().strip().casefold()
        visibility = self.visibility_filter.currentData()
        filtered = []
        for repo in self.repositories:
            if visibility == "private" and not repo.get("private"):
                continue
            if visibility == "public" and repo.get("private"):
                continue
            searchable = " ".join(
                str(repo.get(key) or "") for key in ("name", "full_name", "description")
            )
            searchable += " " + str((repo.get("owner") or {}).get("login", ""))
            if search not in searchable.casefold():
                continue
            filtered.append(repo)
        self.filtered_repositories = filtered
        self.stat_total.setText(str(len(self.repositories)))
        self.stat_public.setText(
            str(sum(not repo.get("private") for repo in self.repositories))
        )
        self.stat_private.setText(
            str(sum(bool(repo.get("private")) for repo in self.repositories))
        )
        cutoff = datetime.now(timezone.utc).timestamp() - 30 * 24 * 60 * 60  # noqa: UP017
        recent = 0
        for repo in self.repositories:
            try:
                updated = datetime.fromisoformat(
                    (repo.get("updated_at") or "").replace("Z", "+00:00")
                )  # noqa: FURB162
                recent += updated.timestamp() >= cutoff
            except ValueError:
                pass
        self.stat_recent.setText(str(recent))
        self.table.setVisible(bool(filtered))
        self.empty_label.setVisible(not filtered)
        self.table.setRowCount(len(filtered))
        for row, repo in enumerate(filtered):
            owner = (repo.get("owner") or {}).get("login", "")
            name_item = QTableWidgetItem(repo.get("name", ""))
            name_item.setToolTip(
                f"{owner}/{repo.get('name', '')} · Doppelklick öffnet GitHub"
            )
            name_item.setData(Qt.ItemDataRole.UserRole, repo)
            values = [
                name_item,
                QTableWidgetItem(repo.get("description") or "—"),
                QTableWidgetItem("Privat" if repo.get("private") else "Öffentlich"),
                QTableWidgetItem(repo.get("language") or "—"),
                QTableWidgetItem(str(repo.get("stargazers_count", 0) or 0)),
                QTableWidgetItem(format_date(repo.get("updated_at"))),
            ]
            for column, item in enumerate(values):
                if column in (4, 5):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 42)
        if filtered:
            self.table.selectRow(0)
        else:
            self.update_action_state()

    def selected_repository(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.filtered_repositories):
            return None
        return self.filtered_repositories[row]

    def update_action_state(self) -> None:
        enabled = self.selected_repository() is not None
        for button in (
            self.files_button,
            self.details_button,
            self.zip_button,
            self.backup_button,
            self.delete_button,
        ):
            button.setEnabled(enabled)

    def open_repository_url(self) -> None:
        repo = self.selected_repository()
        if repo and repo.get("html_url"):
            QDesktopServices.openUrl(QUrl(repo["html_url"]))

    def open_files(self) -> None:
        repo = self.selected_repository()
        if repo and self.api:
            RepoFilesDialog(self, repo).exec()

    def edit_metadata(self) -> None:
        repo = self.selected_repository()
        if not repo or not self.api:
            return
        dialog = MetadataDialog(self, repo)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        client = self.api
        changes = dialog.changes()
        self.run_task(
            lambda: client.update_repository(
                repo["owner"]["login"], repo["name"], changes
            ),
            lambda result: self.metadata_saved(result),
            message="Änderungen werden bei GitHub gespeichert …",
        )

    def metadata_saved(self, repo: dict) -> None:
        QMessageBox.information(
            self,
            "Gespeichert",
            f"Die Details von {repo.get('full_name', repo.get('name'))} wurden aktualisiert.",
        )
        self.load_repositories()

    def download_selected(self, kind: str) -> None:
        repo = self.selected_repository()
        if not repo or not self.api:
            return
        owner, name = repo["owner"]["login"], repo["name"]
        if kind == "bundle" and not shutil.which("git"):
            QMessageBox.warning(
                self,
                "Git nicht gefunden",
                "Für Git-Bundle-Backups muss Git installiert und im PATH verfügbar sein.",
            )
            return
        extension = "zip" if kind == "zip" else "bundle"
        suggested = f"{owner}-{name}.{extension}"
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Archiv speichern" if kind == "zip" else "Git-Backup speichern",
            suggested,
            "ZIP-Archiv (*.zip)" if kind == "zip" else "Git-Bundle (*.bundle)",
        )
        if not destination:
            return
        if not destination.lower().endswith(f".{extension}"):
            destination += f".{extension}"
        client = self.api
        operation = (
            (lambda: client.download_archive(owner, name, destination))
            if kind == "zip"
            else (lambda: client.create_git_bundle(owner, name, destination))
        )

        def done(_result: Any) -> None:
            QMessageBox.information(
                self,
                "Download abgeschlossen",
                f"{'ZIP-Archiv' if kind == 'zip' else 'Git-Backup'} gespeichert unter:\n{destination}",
            )

        self.run_task(
            operation,
            done,
            message="Lade ZIP-Archiv …" if kind == "zip" else "Erstelle Git-Backup …",
        )

    def delete_selected(self) -> None:
        repo = self.selected_repository()
        if not repo or not self.api:
            return
        name = repo["name"]
        confirmation = QMessageBox(self)
        confirmation.setIcon(QMessageBox.Icon.Warning)
        confirmation.setWindowTitle("Repository dauerhaft löschen?")
        confirmation.setText(f"„{repo['full_name']}“ bei GitHub endgültig löschen?")
        confirmation.setInformativeText(
            "Das Repository und seine Inhalte werden dauerhaft gelöscht. Diese Aktion kann nicht rückgängig gemacht werden. "
            "Erstelle vorher ein Git-Backup, wenn du die Daten behalten möchtest.\n\n"
            f"Tippe exakt {name} in das Feld, um fortzufahren:"
        )
        input_box = QLineEdit()
        input_box.setPlaceholderText(name)
        confirmation.layout().addWidget(
            input_box, 1, 1, 1, confirmation.layout().columnCount() - 1
        )
        delete_button = confirmation.addButton(
            "Endgültig löschen", QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_button = confirmation.addButton(
            "Abbrechen", QMessageBox.ButtonRole.RejectRole
        )
        delete_button.setEnabled(False)
        input_box.textChanged.connect(
            lambda value: delete_button.setEnabled(value == name)
        )
        confirmation.setDefaultButton(cancel_button)
        confirmation.exec()
        if confirmation.clickedButton() is not delete_button:
            return
        client = self.api
        self.run_task(
            lambda: client.delete_repository(repo["owner"]["login"], name),
            lambda _result: self.repository_deleted(name),
            message="Repository wird bei GitHub gelöscht …",
        )

    def repository_deleted(self, name: str) -> None:
        QMessageBox.information(
            self, "Repository gelöscht", f"„{name}“ wurde bei GitHub gelöscht."
        )
        self.load_repositories()


STYLESHEET = """
QWidget { background: #11131a; color: #e9eaf0; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }
QMainWindow { background: #11131a; }
QLabel#brand { color: #f5f5f8; font-size: 25px; font-weight: 750; letter-spacing: -1px; }
QLabel#brandSub { color: #777d8d; font-size: 9px; font-weight: 700; letter-spacing: 1.6px; }
QLabel#connectionState, QLabel#connectedState { color: #aeb2bf; background: #1a1c25; border: 1px solid #2b2e39; border-radius: 16px; padding: 8px 13px; }
QLabel#connectedState { color: #a4e8bd; border-color: #294734; }
QLabel#eyebrow { color: #a78bfa; font-size: 10px; font-weight: 750; letter-spacing: 1.8px; }
QLabel#heroTitle { color: #f5f5f8; font-size: 37px; font-weight: 750; letter-spacing: -1.2px; }
QLabel#heroLead { color: #a2a6b3; font-size: 15px; line-height: 1.45; max-width: 500px; }
QLabel#featureStrip { color: #d3d4db; font-size: 12px; font-weight: 650; }
QFrame#connectCard, QFrame#statCard { background: #191b24; border: 1px solid #2c2f3b; border-radius: 15px; }
QLabel#sectionTitle, QLabel#dialogTitle { color: #f3f3f7; font-size: 22px; font-weight: 720; }
QLabel#muted { color: #959aa9; }
QLabel#smallNote { color: #9297a5; font-size: 11px; }
QLabel#securityNote { color: #8fcda4; font-size: 11px; }
QLabel#errorLabel { color: #ff9d9d; }
QLabel#pageTitle { color: #f3f3f7; font-size: 29px; font-weight: 720; }
QLabel#statCaption { color: #858a98; font-size: 9px; font-weight: 750; letter-spacing: 1px; }
QLabel#statValue { color: #f2f2f6; font-size: 23px; font-weight: 700; }
QLineEdit, QPlainTextEdit, QComboBox { background: #10121a; border: 1px solid #343745; border-radius: 8px; padding: 10px 11px; selection-background-color: #7252c9; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #8d70e5; }
QComboBox { min-width: 150px; }
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox QAbstractItemView { background: #1b1d27; selection-background-color: #54408e; border: 1px solid #343745; }
QPushButton { color: #dedfe6; background: #232530; border: 1px solid #353845; border-radius: 8px; padding: 9px 13px; font-weight: 620; }
QPushButton:hover { background: #2b2e3a; border-color: #4a4e5e; }
QPushButton:disabled { color: #656a78; background: #1a1c24; border-color: #2a2d37; }
QPushButton#primaryButton { color: white; background: #7656d8; border: 1px solid #876be1; font-weight: 700; padding: 11px 14px; }
QPushButton#primaryButton:hover { background: #8769e6; }
QPushButton#secondaryButton { background: #1a1c25; }
QPushButton#dangerButton { color: #ffaaaa; background: #25191e; border-color: #57313b; }
QPushButton#dangerButton:hover { background: #362026; }
QPushButton#linkButton { color: #b9a6ff; background: transparent; border: 0; padding: 5px 0; text-align: left; }
QTableWidget { background: #171922; border: 1px solid #2d303b; border-radius: 10px; alternate-background-color: #1a1c25; selection-background-color: #393052; selection-color: #ffffff; outline: 0; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #292c36; }
QHeaderView::section { color: #9398a7; background: #1c1e28; border: 0; border-bottom: 1px solid #343744; padding: 10px 8px; font-size: 10px; font-weight: 750; }
QListWidget { background: #151720; border: 1px solid #30333e; border-radius: 9px; padding: 5px; }
QListWidget::item { padding: 11px 9px; border-bottom: 1px solid #282b35; }
QListWidget::item:selected { background: #332a4c; }
QDialog { background: #151720; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QStatusBar { color: #858a98; background: #10121a; border-top: 1px solid #252833; }
QScrollBar:vertical { background: #14161e; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #414451; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("iGitty")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
