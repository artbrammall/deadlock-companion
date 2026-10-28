import json
import sys
import time
import sqlite3
import tempfile

from ui_theme import build_interface, clear_cards, show_cards
from ui_preview import example_lineup

from roster_dialog import RosterDialog
from datetime import datetime, timezone
from pathlib import Path
from app_paths import ASSET_DIR, DATA_DIR, ensure_data, worker_command
from PySide6.QtGui import QIcon, QFont
from PySide6.QtCore import QProcess, QTimer, Qt, QLockFile
from PySide6.QtWidgets import QApplication, QWidget, QDialog, QMessageBox

from pick_modes import MODES, choose_heroes, choose_balanced, balance_adjustments
from balance_history import BalanceHistory

ROOT = ASSET_DIR


def display_name(name):
    return name.replace("_", " ").title()


class ForesightWindow(QWidget):
    def __init__(self, preview=False):
        super().__init__()
        self.preview = preview
        self.preview_storage = tempfile.TemporaryDirectory(prefix="deadlock-preview-") if preview else None
        self.setWindowTitle("Deadlock Foresight")
        self.setWindowIcon(QIcon(str(ASSET_DIR / "assets" / "foresight.ico")))
        self.resize(600, 680)

        self.payload = None
        self.history = BalanceHistory(Path(self.preview_storage.name) / "preview.db") if preview else BalanceHistory()
        self.balance_session = None
        self.prior_counts = {}
        self.last_history_touch = 0.0
        self.using_previous = False
        self.selection_key = None
        self.selected_heroes = None
        self.closing = False
        self.roster_update_pending = False
        self.last_heartbeat = time.monotonic()

        build_interface(self, MODES)

        self.mode.currentTextChanged.connect(self.mode_changed)
        self.reroll.clicked.connect(self.reroll_pick)

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels
        )
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        if not preview:
            executable, arguments = worker_command()
            self.process.start(executable, arguments)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_worker)
        if not preview:
            self.timer.start(1000)
        else:
            self.log.appendPlainText("Preview mode: example data, no capture or network requests.")
            self.history.set_enabled(True)
            self.balance.setChecked(True)
            self.handle_event(example_lineup())

    def hide_recommendation(self, message):
        self.payload = None
        self.status.setText(message)
        clear_cards(self, "No active recommendation")
        self.reroll.setEnabled(False)

    def read_output(self):
        while self.process.canReadLine():
            line = bytes(self.process.readLine()).decode(
                "utf-8", errors="replace"
            ).strip()

            if not line.startswith("@@EVENT "):
                self.log.appendPlainText(line)
                continue

            try:
                event = json.loads(line[len("@@EVENT "):])
            except json.JSONDecodeError:
                self.hide_recommendation("Invalid update from detector.")
                continue

            self.handle_event(event)

    def handle_event(self, event):
        if self.closing:
            return

        if event["type"] == "heartbeat":
            self.last_heartbeat = time.monotonic()
            if (self.payload is not None and not self.using_previous
                    and self.balance_session is not None
                    and time.monotonic() - self.last_history_touch >= 10):
                try:
                    self.history.touch(self.balance_session)
                    self.last_history_touch = time.monotonic()
                except sqlite3.Error as error:
                    self.log.appendPlainText(f"Count history update failed: {error}")
            return

        if event["type"] == "status":
            message = event["message"].strip()

            # The structured lineup event immediately follows this message.
            if message.startswith("CONFIRMED"):
                return

            keep_previous = (
                message.startswith("PAUSED:")
                or "PAUSE_MENU" in message
                or message.startswith("CHECKING:")
            )

            self.using_previous = keep_previous

            if keep_previous and self.payload is not None:
                self.status.setText(
                    "Using last confirmed lineup | awaiting live verification"
                )
            else:
                self.hide_recommendation(message)

            # Forget the saved selection when leaving the pregame context.
            # Pause/capture gaps only hide it; fresh confirmation is still
            # required before it can be displayed again.
            if any(
                state in message
                for state in ("NOT_PREGAME", "LOADING", "HERO_SELECTION")
            ):
                self.selection_key = None
                self.selected_heroes = None
            return

        if event["type"] == "roster_reloaded":
            self.roster_update_pending = False
            return

        if event["type"] != "lineup":
            return

        # Ignore queued results from before the roster was saved.
        if self.roster_update_pending:
            return

        if not event["ranked"]:
            self.hide_recommendation(
                event["unavailable"] or "Recommendations unavailable."
            )
            return

        self.last_heartbeat = time.monotonic()
        self.payload = event
        self.using_previous = False

        try:
            session_id = self.history.session()
            if session_id != self.balance_session:
                self.selection_key = None
                self.selected_heroes = None
            self.balance_session = session_id
            self.prior_counts = self.history.counts(excluding=session_id)
        except sqlite3.Error as error:
            self.hide_recommendation(f"Could not load recommendation counts: {error}")
            return

        # Sorting makes this independent of lane/portrait order.
        key = (
            event["current_hero"],
            tuple(sorted(event["allies"])),
            tuple(sorted(event["enemies"])),
            tuple(sorted(row["hero"] for row in event["ranked"])),
            self.mode.currentText(),
            self.balance.isChecked(),
            tuple((r["hero"], r["score"], r.get("opportunity_percentile"))
                  for r in sorted(event["ranked"], key=lambda r: r["hero"])),
        )

        if key != self.selection_key or self.selected_heroes is None:
            self.selection_key = key
            self.selected_heroes = self.select_picks(event["ranked"])

        self.render_pick()

    def select_picks(self, rows):
        if self.balance.isChecked():
            return choose_balanced(rows, self.mode.currentText(), self.prior_counts)
        return choose_heroes(rows, self.mode.currentText())

    def balance_changed(self, enabled):
        try:
            self.history.set_enabled(enabled)
        except sqlite3.Error as error:
            self.balance.blockSignals(True)
            self.balance.setChecked(not enabled)
            self.balance.blockSignals(False)
            QMessageBox.warning(self, "Could not save setting", str(error))
            return
        self.mode_changed(None)

    def reset_balance_counts(self):
        if QMessageBox.question(
            self, "Reset counts", "Clear recommendation history? "
            "The current visible #1 will count as the first new entry.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.history.reset()
        except sqlite3.Error as error:
            QMessageBox.warning(self, "Could not reset counts", str(error))
            return
        self.prior_counts = {}
        self.history_label.setText("Recommendation counts reset.")
        self.mode_changed(None)

    def edit_roster(self):
        try:
            dialog = RosterDialog(self, preview=self.preview)
        except (sqlite3.Error, OSError, ValueError) as error:
            QMessageBox.warning(
                self, "Could not load roster", str(error)
            )
            return

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.selection_key = None
        self.selected_heroes = None
        self.using_previous = False

        if self.process.state() != QProcess.ProcessState.Running:
            self.roster_update_pending = False
            self.hide_recommendation(
                "Roster saved. Restart the app to resume detection."
            )
            return

        self.roster_update_pending = True
        self.hide_recommendation(
            "Roster saved. Waiting for a fresh confirmed lineup."
        )

        if self.process.write(b"reload_roster\n") < 0:
            self.roster_update_pending = False
            self.hide_recommendation(
                "Roster saved, but detector update failed. Restart the app."
            )

    def mode_changed(self, _):
        self.selection_key = None
        self.selected_heroes = None

        if self.payload is not None:
            self.selected_heroes = self.select_picks(self.payload["ranked"])
            self.render_pick()

    def reroll_pick(self):
        if self.payload is None or self.mode.currentText() != "Random":
            return

        self.selected_heroes = self.select_picks(self.payload["ranked"])
        self.render_pick()

    def render_pick(self):
        data = self.payload
        rows = data["ranked"]
        mode = self.mode.currentText()
        by_hero = {row["hero"]: row for row in rows}

        current = by_hero[data["current_hero"]]

        downloaded = datetime.fromisoformat(data["downloaded_at"])
        age_hours = max(
            0,
            (datetime.now(timezone.utc) - downloaded).total_seconds() / 3600,
        )

        state_label = (
            "Using last confirmed lineup | awaiting live verification"
            if self.using_previous
            else "Confirmed pregame"
        )

        if self.preview:
            state_label = "PREVIEW · Example pregame"
        self.status.setText(
            f"{state_label} | {mode}\n"
            f"Statistics: {age_hours:.1f} hours old"
        )

        selected = self.selected_heroes or []
        bonuses = (
            balance_adjustments(rows, mode, self.prior_counts)
            if self.balance.isChecked() and mode != "Random" else {}
        )
        if self.balance_session is not None and not self.using_previous:
            try:
                self.history.record(
                    self.balance_session, selected[0] if selected else None
                )
                total = sum(self.prior_counts.values()) + bool(selected)
                self.history_label.setText(
                    f"{total} counted pregame recommendations. "
                    "Latest #1 replaces this pregame's entry; rescans add nothing."
                )
            except sqlite3.Error as error:
                self.history_label.setText(f"Could not save #1 count: {error}")

        show_cards(self, data, selected, bonuses)
        self.reroll.setEnabled(mode == "Random")

    def check_worker(self):
        # Hide stale recommendations if the capture process hangs.
        if (
            self.payload is not None
            and time.monotonic() - self.last_heartbeat > 10
        ):
            self.hide_recommendation(
                "Detector stopped responding. Close and restart the app."
            )
            self.process.kill()

    def process_error(self, _):
        self.hide_recommendation(
            f"Detector error: {self.process.errorString()}"
        )

    def process_finished(self, *_):
        self.hide_recommendation("Detection stopped. See the log below.")
        if self.closing:
            self.close()

    def closeEvent(self, event):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.timer.stop()
            if self.preview_storage is not None:
                self.preview_storage.cleanup()
            event.accept()
            return

        event.ignore()
        if self.closing:
            return

        self.closing = True
        self.hide_recommendation("Stopping detection...")
        self.mode.setEnabled(False)
        self.edit_roster_button.setEnabled(False)
        self.balance.setEnabled(False)
        self.reset_counts_button.setEnabled(False)
        self.process.write(b"stop\n")

        # A network request may still be running during startup.
        QTimer.singleShot(5000, self.force_stop)

    def force_stop(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()


def main():
    import logging
    from logging.handlers import RotatingFileHandler
    import os
    import traceback
    application = QApplication(sys.argv)
    application.setApplicationName("Deadlock Foresight")
    application.setFont(QFont("Segoe UI", 10))
    preview = "--preview" in sys.argv
    lock = None
    try:
        if not preview:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            lock = QLockFile(str(DATA_DIR / 'application.lock'))
            if not lock.tryLock(0):
                QMessageBox.information(None, 'Deadlock Foresight',
                                        'Deadlock Foresight is already running, or its data folder is locked.')
                return 0
            ensure_data()
            logger = logging.getLogger('foresight')
            logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(DATA_DIR / 'app.log', maxBytes=2_000_000,
                                          backupCount=2, encoding='utf-8')
            logger.addHandler(handler)
            def report_error(kind, value, tb):
                logger.error('Unhandled exception', exc_info=(kind, value, tb))
                QMessageBox.critical(None, 'Deadlock Foresight',
                                     f'{value}\n\nDetails saved to {DATA_DIR / "app.log"}')
            sys.excepthook = report_error
        # Windowed PyInstaller builds do not provide console streams.
        for stream in ('stdout', 'stderr'):
            if getattr(sys, stream) is None:
                setattr(sys, stream, open(os.devnull, 'w', encoding='utf-8'))
        window = ForesightWindow(preview=preview)
        window.show()
        return application.exec()
    except Exception as error:
        QMessageBox.critical(None, 'Deadlock Foresight could not start', str(error))
        return 1
    finally:
        if lock is not None:
            lock.unlock()


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
