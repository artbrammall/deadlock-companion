import json
import sys
import time
import sqlite3

from roster_dialog import RosterDialog
from datetime import datetime, timezone
from pathlib import Path
from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QDialog,
    QMessageBox,
)

from pick_modes import MODES, choose_heroes, choose_balanced, balance_adjustments
from balance_history import BalanceHistory

ROOT = Path(__file__).resolve().parent


def display_name(name):
    return name.replace("_", " ").title()


class CompanionWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Deadlock Companion")
        self.resize(600, 680)

        self.payload = None
        self.history = BalanceHistory()
        self.balance_session = None
        self.prior_counts = {}
        self.last_history_touch = 0.0
        self.using_previous = False
        self.selection_key = None
        self.selected_heroes = None
        self.closing = False
        self.roster_update_pending = False
        self.last_heartbeat = time.monotonic()

        self.status = QLabel("Starting detection and loading statistics...")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)

        self.mode = QComboBox()
        self.mode.addItems(MODES)
        self.mode.setCurrentText("Best Opportunity")

        self.suggestion = QLabel("Waiting for a confirmed pregame lineup")
        self.suggestion.setWordWrap(True)
        self.suggestion.setStyleSheet("font-size: 24px; font-weight: bold;")

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)

        self.reroll = QPushButton("Reroll")
        self.reroll.setEnabled(False)

        notice = QLabel(
            "Scores are estimates, not win probabilities.\n"
            "Enemy picks may have changed. Confirm availability in-game."
        )
        notice.setWordWrap(True)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(150)
        self.log.setMaximumHeight(140)

        self.edit_roster_button = QPushButton("Edit roster")
        self.edit_roster_button.clicked.connect(self.edit_roster)

        self.balance = QCheckBox("Balance roster")
        self.balance.setChecked(self.history.enabled())
        self.balance.setToolTip(
            "Favour heroes with fewer previous #1 recommendations. "
            "Counts are recorded with the toggle on or off."
        )
        self.balance.toggled.connect(self.balance_changed)
        self.reset_counts_button = QPushButton("Reset counts")
        self.reset_counts_button.clicked.connect(self.reset_balance_counts)
        self.history_label = QLabel("#1 counts start with this update.")
        self.history_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        for widget in (
            self.status,
            self.mode,
            self.edit_roster_button,
            self.balance,
            self.reset_counts_button,
            self.history_label,
            self.suggestion,
            self.details,
            self.reroll,
            notice,
            self.log,
        ):
            layout.addWidget(widget)

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
        self.process.start(
            sys.executable,
            ["-u", str(ROOT / "live_detection.py"), "--gui"],
        )

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_worker)
        self.timer.start(1000)

    def hide_recommendation(self, message):
        self.payload = None
        self.status.setText(message)
        self.suggestion.setText("No active recommendation")
        self.details.clear()
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
            dialog = RosterDialog(self)
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

        self.status.setText(
            f"{state_label} | {mode}\n"
            f"Statistics: {age_hours:.1f} hours old"
        )

        headings = []
        details = [
            f"You: {display_name(data['current_hero'])} "
            f"(ally slot {data['self_slot'] + 1})",
            f"Current hero score: {current['score']:.2f} points",
            "",
        ]

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

        for position, hero in enumerate(selected, start=1):
            result = by_hero[hero]
            is_current = hero == data["current_hero"]
            label = (
                f"Stay on {display_name(hero)}"
                if is_current
                else display_name(hero)
            )

            difference = result["score"] - current["score"]
            # Avoid displaying "-0.00".
            if abs(difference) < 0.005:
                difference = 0.0

            heading = f"{position}. {label}"
            if mode == "Competitive" and not is_current:
                heading += f" ({difference:+.2f} points vs staying)"

            headings.append(heading)
            details.extend([
                f"{position}. {label}",
                f"   Total score: {result['score']:.2f} points",
            ])

            if mode == "Competitive":
                details.append(
                    "   Current hero: comparison baseline"
                    if is_current
                    else f"   Score difference vs staying: "
                         f"{difference:+.2f} points"
                )

            details.extend([
                f"   Overall baseline: {result['baseline_pct']:.2f}",
                f"   Enemy adjustment: {result['matchup_points']:+.2f}",
                f"   Ally adjustment: {result['synergy_points']:+.2f}",
            ])

            details.append(
                f"   Previous #1 recommendations: {self.prior_counts.get(hero, 0)}"
            )
            if hero in bonuses:
                unit = "score points" if mode == "Competitive" else "percentile points"
                details.append(
                    f"   Balance boost: +{bonuses[hero]:.2f} {unit} (preference only)"
                )

            if "opportunity_percentile" in result:
                reference_count = result["opportunity_reference_count"]
                downloaded_at = datetime.fromisoformat(
                    result["opportunity_reference_downloaded_at"]
                )
                reference_age = max(
                    0,
                    (
                        datetime.now(timezone.utc) - downloaded_at
                    ).total_seconds() / 3600,
                )

                details.extend([
                    "   Opportunity percentile: "
                    f"{result['opportunity_percentile']:.1f}",
                    "   Above this hero's typical situation: "
                    f"{result['above_typical_points']:+.3f} points",
                    f"   Reference: {reference_count:,} actual matches",
                    f"   Lineups downloaded {reference_age:.1f} hours ago",
                ])

                if reference_count < 500:
                    details.append(
                        "   Limited reference sample; percentile is less stable."
                    )

            if result["missing"]:
                details.append(
                    "   Missing pair data: " + ", ".join(result["missing"])
                )

            details.append("")

        if mode == "Competitive":
            details.extend([
                ("Ranked by score plus balance boost."
                 if self.balance.isChecked() else "Ranked by total score."),
                "Differences compare model scores, not win probabilities.",
                "A higher score does not guarantee a better pick.",
            ])

        elif mode == "Random":
            details.append(
                "Random options weighted toward less-recommended heroes."
                if self.balance.isChecked()
                else "Random options, not ranked by score."
            )

        elif mode == "Best Opportunity":
            details.extend([
                ("Ranked by opportunity percentile plus balance boost."
                 if self.balance.isChecked()
                 else "Ranked against situations where each hero actually played."),
                "Percentiles are not win probabilities.",
                "A favourable opportunity can still be a weaker",
                "competitive pick than another hero.",
            ])

        self.suggestion.setText(
            "\n".join(headings)
            if headings
            else "Best Opportunity unavailable: reference data incomplete"
        )
        self.details.setPlainText("\n".join(details))
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CompanionWindow()
    window.show()
    sys.exit(app.exec())
