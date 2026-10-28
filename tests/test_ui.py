"""Exercise UI state transitions without capture or real user storage."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QMessageBox
from app import CompanionWindow
from roster_dialog import RosterDialog
from ui_preview import example_lineup
from ui_theme import Portrait


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = CompanionWindow(preview=True)
        self.w.show(); self.qt.processEvents()

    def tearDown(self):
        self.w.close(); self.qt.processEvents()

    def test_preview_starts_no_worker_and_uses_temporary_history(self):
        self.assertEqual(self.w.process.state(), QProcess.ProcessState.NotRunning)
        self.assertFalse(self.w.timer.isActive())
        self.assertEqual(self.w.history.path.parent, Path(self.w.preview_storage.name))
        self.assertEqual([c.hero for c in self.w.pick_cards], ['haze','wraith','dynamo'])
        self.assertIn('PREVIEW', self.w.status.text())

    def test_modes_reroll_and_balance_keep_one_session_entry(self):
        self.w.mode.setCurrentText('Competitive')
        self.assertEqual(self.w.pick_cards[0].hero, 'baba')
        self.assertFalse(self.w.reroll.isEnabled())
        self.w.mode.setCurrentText('Random')
        self.assertTrue(self.w.reroll.isEnabled())
        for _ in range(10):
            self.w.reroll_pick()
            self.assertEqual(len({c.hero for c in self.w.pick_cards}), 3)
        self.w.balance.setChecked(False)
        self.assertEqual(sum(self.w.history.counts().values()), 1)

    def test_rescans_preserve_disclosure_and_do_not_add_counts(self):
        self.w.pick_cards[0].disclosure.button.setChecked(True)
        for _ in range(3): self.w.handle_event(example_lineup())
        self.assertTrue(self.w.pick_cards[0].disclosure.button.isChecked())
        self.assertEqual(sum(self.w.history.counts().values()), 1)

    def test_pause_is_labelled_stale_then_incomplete_clears_cards(self):
        self.w.handle_event({'type':'status', 'message':'PAUSED: capture stale'})
        self.assertIn('last confirmed', self.w.status.text())
        self.assertEqual(len(self.w.pick_cards), 3)
        previous_cards = list(self.w.pick_cards)
        self.w.handle_event({'type':'status', 'message':'WAITING: no complete, unique 6v6 lineup detected.'})
        self.assertTrue(all(card.isHidden() for card in previous_cards))
        self.assertEqual(self.w.pick_cards, [])
        self.assertIsNone(self.w.payload)
        self.assertFalse(self.w.reroll.isEnabled())

    def test_reset_preserves_single_current_entry(self):
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.w.reset_balance_counts()
        self.assertEqual(sum(self.w.history.counts().values()), 1)

    def test_missing_opportunity_data_displays_empty_state(self):
        data = example_lineup()
        for row in data['ranked']: row.pop('opportunity_percentile')
        self.w.handle_event(data)
        self.assertEqual(self.w.pick_cards, [])
        self.assertEqual(sum(self.w.history.counts().values()), 0)

    def test_roster_preview_does_not_read_or_write_real_roster(self):
        with patch('roster_dialog.get_roster', side_effect=AssertionError('real database read')), patch('roster_dialog.set_roster', side_effect=AssertionError('real database write')):
            dialog = RosterDialog(self.w, preview=True)
            self.assertEqual(dialog.heroes.count(), 44)
            dialog.save(); dialog.close()

    def test_missing_artwork_falls_back_to_text(self):
        portrait = Portrait('no_such_hero')
        self.assertTrue(portrait.text())

    def test_close_releases_preview_storage(self):
        directory = Path(self.w.preview_storage.name)
        self.w.close()
        self.assertFalse(directory.exists())


if __name__ == '__main__':
    unittest.main()
