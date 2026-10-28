import sqlite3
import json
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtCore import QSize
from ui_theme import STYLE

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from roster import available_heroes, get_roster, set_roster


class RosterDialog(QDialog):
    def __init__(self, parent=None, preview=False):
        super().__init__(parent)
        self.setWindowTitle("Edit roster")
        self.resize(440, 640)
        self.preview = preview
        self.setStyleSheet(STYLE)

        root = Path(__file__).resolve().parent
        heroes = sorted(json.loads((root / "hero_ids.json").read_text())) if preview else sorted(available_heroes())
        saved = set(heroes) if preview else set(get_roster())

        explanation = QLabel(
            "Choose heroes you want recommended.\n"
            "Your current hero is always included as a stay option.\n"
            "An empty roster leaves only the stay option."
        )
        explanation.setWordWrap(True)

        self.heroes = QListWidget()
        self.heroes.setIconSize(QSize(35, 47))
        for hero in heroes:
            item = QListWidgetItem(hero.replace("_", " ").title())
            item.setIcon(QIcon(str(root / "assets" / "hero_portraits" / f"{hero}.png")))
            item.setData(Qt.ItemDataRole.UserRole, hero)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked
                if hero in saved
                else Qt.CheckState.Unchecked
            )
            self.heroes.addItem(item)

        self.count = QLabel()
        self.heroes.itemChanged.connect(self.update_count)

        select_all = QPushButton("Select all")
        clear_all = QPushButton("Clear all")
        select_all.clicked.connect(
            lambda: self.set_all(Qt.CheckState.Checked)
        )
        clear_all.clicked.connect(
            lambda: self.set_all(Qt.CheckState.Unchecked)
        )

        selection_buttons = QHBoxLayout()
        selection_buttons.addWidget(select_all)
        selection_buttons.addWidget(clear_all)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        if preview:
            buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
            explanation.setText("Preview roster editor. Saving is disabled here; your real roster is untouched.")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addLayout(selection_buttons)
        layout.addWidget(self.heroes)
        layout.addWidget(self.count)
        layout.addWidget(buttons)

        self.update_count()

    def selected_heroes(self):
        return [
            self.heroes.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.heroes.count())
            if self.heroes.item(index).checkState()
            == Qt.CheckState.Checked
        ]

    def update_count(self, *_):
        self.count.setText(
            f"{len(self.selected_heroes())} heroes selected"
        )

    def set_all(self, state):
        self.heroes.blockSignals(True)
        try:
            for index in range(self.heroes.count()):
                self.heroes.item(index).setCheckState(state)
        finally:
            self.heroes.blockSignals(False)
        self.update_count()

    def save(self):
        if self.preview:
            return
        try:
            set_roster(self.selected_heroes())
        except (sqlite3.Error, OSError, ValueError) as error:
            QMessageBox.warning(
                self, "Could not save roster", str(error)
            )
            return

        self.accept()