import random
import tempfile
import unittest
from pathlib import Path

from balance_history import BalanceHistory
from pick_modes import choose_balanced, choose_heroes, balance_adjustments


class BalancingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'companion.db'
        self.history = BalanceHistory(self.path)
        self.rows = [
            {'hero': 'a', 'score': 55, 'opportunity_percentile': 90, 'above_typical_points': .5},
            {'hero': 'b', 'score': 52, 'opportunity_percentile': 75, 'above_typical_points': .3},
            {'hero': 'c', 'score': 44, 'opportunity_percentile': 10, 'above_typical_points': -.3},
        ]

    def test_equal_counts_preserve_ranked_modes(self):
        for mode in ('Competitive', 'Best Opportunity'):
            self.assertEqual(choose_balanced(self.rows, mode, {}), choose_heroes(self.rows, mode))

    def test_underuse_can_outweigh_small_score_gap(self):
        result = choose_balanced(self.rows, 'Competitive', {'a': 3, 'b': 0, 'c': 3})
        self.assertEqual(result[0], 'b')
        self.assertEqual(self.rows[0]['score'], 55)

    def test_lineup_still_matters(self):
        result = choose_balanced(self.rows, 'Competitive', {'a': 1, 'b': 0, 'c': 0})
        self.assertEqual(result[0], 'a')

    def test_missing_reference_stays_unavailable(self):
        rows = [{'hero': 'a', 'score': 55}]
        self.assertEqual(choose_balanced(rows, 'Best Opportunity', {}), [])

    def test_random_has_no_duplicates_and_prefers_underused(self):
        rng = random.Random(123)
        first = {'a': 0, 'b': 0, 'c': 0}
        for _ in range(1000):
            picks = choose_balanced(self.rows, 'Random', {'a': 20}, rng=rng)
            self.assertEqual(len(picks), len(set(picks)))
            first[picks[0]] += 1
        self.assertGreater(first['b'], first['a'] * 5)

    def test_record_replaces_current_session(self):
        session = self.history.session(1000)
        for _ in range(10):
            self.history.record(session, 'a')
        self.assertEqual(self.history.counts(), {'a': 1})
        self.assertEqual(self.history.counts(excluding=session), {})
        self.history.record(session, 'b')
        self.assertEqual(self.history.counts(), {'b': 1})

    def test_restart_reuses_recent_session(self):
        session = self.history.session(1000)
        self.history.record(session, 'a')
        reopened = BalanceHistory(self.path)
        self.assertEqual(reopened.session(1050), session)
        self.assertEqual(reopened.counts(), {'a': 1})

    def test_gap_starts_new_session(self):
        first = self.history.session(1000)
        self.history.record(first, 'a')
        second = self.history.session(1121)
        self.assertNotEqual(first, second)
        self.history.record(second, 'a')
        self.assertEqual(self.history.counts(), {'a': 2})

    def test_activity_keeps_session_alive(self):
        session = self.history.session(1000)
        self.history.touch(session, 1110)
        self.assertEqual(self.history.session(1200), session)

    def test_reset_and_setting_persistence(self):
        session = self.history.session(1000)
        self.history.record(session, 'a')
        self.history.set_enabled(True)
        self.history.reset()
        self.assertEqual(self.history.counts(), {})
        self.assertTrue(BalanceHistory(self.path).enabled())

    def test_empty_candidates(self):
        for mode in ('Competitive', 'Best Opportunity', 'Random'):
            self.assertEqual(choose_balanced([], mode, {}), [])

    def test_bonus_proportional_to_count_gap(self):
        bonus = balance_adjustments(self.rows, 'Competitive', {'a': 4, 'b': 2, 'c': 0})
        self.assertEqual(bonus, {'a': 0, 'b': 4, 'c': 8})


if __name__ == '__main__':
    unittest.main()
