from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from gitea_client import validate_gitea_name


class GiteaMirrorDialog(QDialog):
    """Collect the settings for creating a Gitea-native pull mirror."""

    def __init__(
        self, parent: QDialog | None, source_repo: dict, default_owner: str
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gitea-Pull-Mirror anlegen")
        self.setMinimumWidth(620)

        source_owner = str(source_repo.get("owner", ""))
        if isinstance(source_repo.get("owner"), dict):
            source_owner = str(source_repo["owner"].get("login", ""))
        source_name = str(source_repo.get("name", ""))
        source_private = bool(source_repo.get("private", False))
        self._source_private = source_private

        root = QVBoxLayout(self)
        root.setSpacing(12)

        source_box = QGroupBox("Quelle")
        source_layout = QFormLayout(source_box)
        source_layout.addRow(
            "GitHub-Repository:", self._plain_label(f"{source_owner}/{source_name}")
        )
        source_layout.addRow(
            "Gitea-Zielserver:", self._plain_label("http://127.0.0.1:3000")
        )
        root.addWidget(source_box)

        destination_box = QGroupBox("Ziel-Repository")
        destination_layout = QFormLayout(destination_box)
        self.owner_edit = QLineEdit(str(default_owner).strip())
        self.owner_edit.setPlaceholderText("Gitea-Benutzername")
        self.name_edit = QLineEdit(source_name)
        self.name_edit.setPlaceholderText("Repository-Name")
        destination_layout.addRow("Gitea-Besitzer:", self.owner_edit)
        destination_layout.addRow("Repository-Name:", self.name_edit)
        root.addWidget(destination_box)

        self.private_checkbox = QCheckBox("Ziel-Repository privat anlegen")
        self.private_checkbox.setChecked(True)
        if source_private:
            self.private_checkbox.setChecked(True)
            self.private_checkbox.setEnabled(False)
        root.addWidget(self.private_checkbox)

        mirror_note = self._plain_label(
            "Gitea richtet einen nativen, regelmäßigen PULL-Mirror ein. "
            "Das Abrufintervall kommt aus der Gitea-Servereinstellung. "
            "Übertragen werden nur Branches, Tags und Commits; Issues, Releases "
            "und Einstellungen werden nicht übernommen. GitHub und lokale Ordner "
            "werden nicht verändert. Ein bereits vorhandenes Repository wird nie "
            "überschrieben."
        )
        mirror_note.setWordWrap(True)
        root.addWidget(mirror_note)

        token_note = self._plain_label(
            "Wichtiger Hinweis: Mit der folgenden Option kann der aktive "
            "GitHub-Token an Gitea übergeben werden. Gitea speichert ihn für "
            "zukünftige Abrufe des Mirrors."
        )
        token_note.setWordWrap(True)
        token_note.setStyleSheet("font-weight: bold;")
        root.addWidget(token_note)

        self.token_checkbox = QCheckBox(
            "Aktiven GitHub-Token für zukünftige Mirror-Abrufe an Gitea übergeben"
        )
        self.token_checkbox.setChecked(False)
        root.addWidget(self.token_checkbox)

        if source_private:
            consent_note = self._plain_label(
                "Für private Quellen ist diese ausdrückliche Einwilligung erforderlich, "
                "bevor der Pull-Mirror angelegt werden kann."
            )
            consent_note.setWordWrap(True)
            consent_note.setStyleSheet("font-weight: bold; color: #8b0000;")
            root.addWidget(consent_note)

        buttons = QDialogButtonBox()
        self.cancel_button = buttons.addButton(
            "Abbrechen", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.create_button = buttons.addButton(
            "Pull-Mirror anlegen", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.rejected.connect(self.reject)
        self.create_button.clicked.connect(self.validate_and_accept)
        root.addWidget(buttons)

    @staticmethod
    def _plain_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def validate_and_accept(self) -> bool:
        """Validate editable values and close successfully only on valid input."""
        try:
            owner = validate_gitea_name(self.owner_edit.text().strip())
            name = validate_gitea_name(self.name_edit.text().strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Ungültige Eingabe", str(exc))
            return False

        if self._source_private and not self.token_checkbox.isChecked():
            QMessageBox.warning(
                self,
                "Einwilligung erforderlich",
                "Für ein privates Quell-Repository muss die Übergabe des aktiven "
                "GitHub-Tokens ausdrücklich bestätigt werden.",
            )
            return False

        # Keep the validated, stripped values in the controls before accepting.
        self.owner_edit.setText(owner)
        self.name_edit.setText(name)
        self.accept()
        return True

    def values(self) -> dict:
        """Return the user-selected mirror settings with trimmed text fields."""
        return {
            "target_owner": self.owner_edit.text().strip(),
            "target_name": self.name_edit.text().strip(),
            "private": self.private_checkbox.isChecked(),
            "include_github_token": self.token_checkbox.isChecked(),
        }
