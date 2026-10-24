import sqlite3

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit roster")
        self.resize(380, 560)

        saved = set(get_roster())

        explanation = QLabel(
            "Choose heroes you want recommended.\n"
            "Your current hero is always included as a stay option.\n"
            "An empty roster leaves only the stay option."
        )
        explanation.setWordWrap(True)

        self.heroes = QListWidget()
        for hero in sorted(available_heroes()):
            item = QListWidgetItem(hero.replace("_", " ").title())
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
        try:
            set_roster(self.selected_heroes())
        except (sqlite3.Error, OSError, ValueError) as error:
            QMessageBox.warning(
                self, "Could not save roster", str(error)
            )
            return

        self.accept()