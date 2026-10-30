from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import (
    QDir,
    QFileInfo,
    QModelIndex,
    QSignalBlocker,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


class _GermanFileSystemModel(QFileSystemModel):
    """Filesystem model with compact German column names."""

    HEADERS = ("Name", "Größe", "Typ", "Geändert")

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self.HEADERS)
        ):
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)


class LocalFilesPane(QWidget):
    """A safe, read-only local file browser for the local side of iGitty.

    The pane deliberately exposes navigation and opening only: it does not
    provide delete, move, copy, or rename operations.
    """

    pathChanged = Signal(str)
    selectionChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("localPane")

        self._home = self._resolve_directory(str(Path.home()))
        self._path = self._home
        self._building_roots = False

        self.path_edit = QLineEdit(self._path)
        self.path_edit.setObjectName("localPath")
        self.path_edit.setClearButtonEnabled(True)
        self.path_edit.setPlaceholderText("Lokaler Pfad")
        self.path_edit.returnPressed.connect(self._navigate_from_field)

        self.up_button = QToolButton()
        self.up_button.setText("↑")
        self.up_button.setToolTip("Übergeordneten Ordner")
        self.up_button.setAccessibleName("Übergeordneter Ordner")
        self.up_button.clicked.connect(self.go_up)

        self.home_button = QToolButton()
        self.home_button.setText("⌂")
        self.home_button.setToolTip("Benutzerordner")
        self.home_button.setAccessibleName("Benutzerordner")
        self.home_button.clicked.connect(lambda: self._set_path(self._home))

        self.choose_button = QPushButton("Ordner …")
        self.choose_button.setToolTip("Ordner auswählen")
        self.choose_button.clicked.connect(self.choose_directory)

        self.refresh_button = QToolButton()
        self.refresh_button.setText("↻")
        self.refresh_button.setToolTip("Aktualisieren")
        self.refresh_button.setAccessibleName("Aktualisieren")
        self.refresh_button.clicked.connect(self.refresh)

        self.root_selector = QComboBox()
        self.root_selector.setToolTip("Laufwerk oder Dateisystemwurzel")
        self.root_selector.setMaximumWidth(120)
        self.root_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.root_selector.currentIndexChanged.connect(self._root_selected)
        self._populate_roots()

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)
        toolbar.addWidget(self.up_button)
        toolbar.addWidget(self.home_button)
        toolbar.addWidget(self.path_edit, 1)
        toolbar.addWidget(self.root_selector)
        toolbar.addWidget(self.choose_button)
        toolbar.addWidget(self.refresh_button)

        self.model = _GermanFileSystemModel(self)
        self.model.setFilter(
            QDir.Filter.AllEntries | QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot
        )
        self.model.setReadOnly(True)
        self.model.setNameFilterDisables(False)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            "Dateien filtern (z. B. *.py) · Ordner bleiben sichtbar"
        )
        self.filter_edit.textChanged.connect(
            lambda text: self.model.setNameFilters(text.split() if text.strip() else [])
        )

        self.files_view = QTreeView(self)
        self.files_view.setObjectName("localFilesView")
        self.files_view.setModel(self.model)
        self.files_view.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.files_view.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.files_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.files_view.setRootIsDecorated(False)
        self.files_view.setItemsExpandable(False)
        self.files_view.setSortingEnabled(True)
        self.files_view.setAlternatingRowColors(True)
        self.files_view.setUniformRowHeights(True)
        self.files_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.files_view.activated.connect(self._activated)
        self.files_view.clicked.connect(self._selection_changed)
        self.files_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.files_view.header().setStretchLastSection(True)
        self.files_view.header().setMinimumSectionSize(70)
        self.files_view.setColumnWidth(0, 290)
        self.files_view.setColumnWidth(1, 90)
        self.files_view.setColumnWidth(2, 130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(4)
        title = QLabel("RECHTS · LOKALE ORDNER")
        title.setObjectName("paneTitle")
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.files_view, 1)
        layout.addWidget(QLabel("Lokales Dateisystem · Doppelklick zum Öffnen"))

        self._set_path(self._home, emit=False)

    def _resolve_directory(self, value: str) -> str:
        return os.path.realpath(os.path.abspath(os.path.expanduser(value)))

    def _populate_roots(self) -> None:
        self._building_roots = True
        self.root_selector.clear()
        roots: list[str] = [self._home]
        if sys.platform.startswith("win"):
            roots.extend(QFileInfo(d).absoluteFilePath() for d in QDir.drives())
        else:
            roots.append(os.path.abspath(os.sep))
        seen: set[str] = set()
        for root in roots:
            resolved = self._resolve_directory(root)
            if resolved not in seen and os.path.isdir(resolved):
                seen.add(resolved)
                label = "Benutzerordner" if resolved == self._home else resolved
                self.root_selector.addItem(label, resolved)
        self._building_roots = False
        self._sync_root_selector()

    def _sync_root_selector(self) -> None:
        chosen = -1
        longest = -1
        for index in range(self.root_selector.count()):
            root = self.root_selector.itemData(index)
            try:
                matches = os.path.commonpath([root, self._path]) == root
            except ValueError:
                matches = False
            if matches and len(root) > longest:
                chosen, longest = index, len(root)
        with QSignalBlocker(self.root_selector):
            self.root_selector.setCurrentIndex(chosen)

    def _root_selected(self, index: int) -> None:
        if not self._building_roots and index >= 0:
            value = self.root_selector.itemData(index)
            if value:
                self._set_path(str(value))

    def _navigate_from_field(self) -> None:
        value = self.path_edit.text().strip()
        if value:
            self._set_path(value)
        else:
            self.path_edit.setText(self._path)

    def _set_path(self, value: str, *, emit: bool = True) -> bool:
        candidate = self._resolve_directory(value)
        if not os.path.isdir(candidate) or not os.access(candidate, os.R_OK):
            self.path_edit.setText(self._path)
            return False
        changed = candidate != self._path
        self._path = candidate
        self.path_edit.setText(candidate)
        self.up_button.setEnabled(os.path.dirname(candidate) != candidate)
        self._sync_root_selector()
        root_index = self.model.setRootPath(candidate)
        self.files_view.setRootIndex(root_index)
        self.files_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        if changed and emit:
            self.pathChanged.emit(candidate)
        return True

    def current_path(self) -> str:
        """Return the normalized absolute path currently displayed."""
        return self._path

    def selected_path(self) -> str | None:
        index = self.files_view.currentIndex()
        if not index.isValid():
            return None
        path = self.model.filePath(index)
        return (
            self._resolve_directory(path)
            if os.path.isdir(path)
            else os.path.realpath(os.path.abspath(path))
        )

    def _selection_changed(self, index: QModelIndex) -> None:
        path = self.selected_path()
        if path:
            self.selectionChanged.emit(path)

    def go_up(self) -> None:
        parent = os.path.dirname(self._path)
        if parent and parent != self._path:
            self._set_path(parent)

    def choose_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Lokalen Ordner auswählen", self._path
        )
        if selected:
            self._set_path(selected)

    def refresh(self) -> None:
        """Refresh the model without showing an error dialog."""
        self.model.setRootPath("")
        self._set_path(self._path, emit=False)

    def _activated(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self._set_path(path)
        elif os.path.isfile(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.realpath(path)))

    def open_selected(self) -> None:
        """Navigate into the selected directory or open the selected file."""
        index = self.files_view.currentIndex()
        if index.isValid():
            self._activated(index)


__all__ = ["LocalFilesPane"]
