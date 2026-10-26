import json
import unittest
from pathlib import Path

import cv2
import numpy as np

from recognition import HeroRecognizer
from ranked_gate import RankedPregameGate
from screen_state import ScreenStateDetector
from self_detection import detect_self

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "tests" / "samples"
ALLIES = ["bebop", "seven", "venator", "nurse_harrow", "shiv", "vyper"]
ENEMIES = ["haze", "calico", "lash", "rem", "yamato", "victor"]


class RankedCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = json.loads((ROOT / "screen_config.json").read_text())["layouts"]["ranked"]
        cls.recognizer = HeroRecognizer(ROOT / "portraits")
        cls.detector = ScreenStateDetector(ROOT / "screen_templates")

    def frame(self, name):
        frame = cv2.imread(str(SAMPLES / name))
        self.assertIsNotNone(frame)
        return frame

    def labels(self, name):
        results = self.recognizer.recognize_teams(self.frame(name), self.layout)
        return {team: [r["hero"] for r in rows] for team, rows in results.items()}

    def test_tab_identifies_both_teams(self):
        self.assertEqual(self.labels("competitive_pregame_tab.png"),
                         {"ally": ALLIES, "enemy": ENEMIES})

    def test_lane_switch_and_banner(self):
        teams = self.labels("competitive_lane_switch.png")
        self.assertEqual(teams["ally"], ALLIES)
        self.assertEqual(teams["enemy"], ["victor", "calico", "yamato", "rem", "haze", "lash"])
        self.assertEqual(set(teams["enemy"]), set(ENEMIES))

    def test_obscured_first_frame_fails_closed(self):
        teams = self.labels("competitive_pregame.png")
        self.assertEqual(teams["ally"], ALLIES)
        self.assertEqual(teams["enemy"], ["UNKNOWN"] + ENEMIES[1:])

    def test_ranked_state_and_self(self):
        for name in ("competitive_pregame.png", "competitive_pregame_tab.png",
                     "competitive_lane_switch.png"):
            with self.subTest(name=name):
                frame = self.frame(name)
                self.assertEqual(self.detector.detect(frame)[0], "PREGAME")
                self.assertEqual(detect_self(frame, self.layout), 2)
        self.assertEqual(self.detector.detect(self.frame("competitive_teams.png"))[0],
                         "NOT_PREGAME")

    def test_fallback_rejects_blank_and_noise(self):
        rng = np.random.default_rng(43)
        images = [np.full((88, 74, 3), v, np.uint8) for v in (0, 80, 255)]
        images += [rng.integers(0, 256, (88, 74, 3), dtype=np.uint8) for _ in range(20)]
        for first in (False, True):
            for index, image in enumerate(images):
                with self.subTest(first=first, index=index):
                    result = self.recognizer.recognize_faded(image, first)
                    self.assertEqual(result["hero"], "UNKNOWN")

    def test_all_loading_portraits_rejected(self):
        teams = self.labels("competitive_teams.png")
        self.assertTrue(all(h == "UNKNOWN" for rows in teams.values() for h in rows))


class RankedGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = RankedPregameGate(ROOT / "screen_templates")

    def frame(self, name):
        frame = cv2.imread(str(SAMPLES / name))
        self.assertIsNotNone(frame)
        return frame

    def test_gate_requires_evidence_before_tab(self):
        self.assertFalse(self.gate.update(self.frame("competitive_pregame_tab.png"), "PREGAME", 0))
        self.assertTrue(self.gate.update(self.frame("competitive_pregame.png"), "PREGAME", 1))
        self.assertTrue(self.gate.update(self.frame("competitive_pregame_tab.png"), "PREGAME", 2))
        self.assertTrue(self.gate.update(self.frame("competitive_lane_switch.png"), "PREGAME", 3))

    def test_old_samples_cannot_unlock_gate(self):
        for file in SAMPLES.glob("*.png"):
            if file.name == "competitive_pregame.png" or file.name.startswith("ranked_dropout_"):
                continue
            with self.subTest(name=file.name):
                self.assertLess(self.gate.marker_score(self.frame(file.name)), 0.85)

    def test_loading_clears_evidence_immediately(self):
        self.gate.update(self.frame("competitive_pregame.png"), "PREGAME", 0)
        self.assertFalse(self.gate.update(self.frame("competitive_teams.png"), "LOADING", 1))
        self.assertFalse(self.gate.update(self.frame("competitive_pregame_tab.png"), "PREGAME", 2))

    def test_brief_unknown_transition_preserves_only_mode_evidence(self):
        self.gate.update(self.frame("competitive_pregame.png"), "PREGAME", 0)
        self.assertFalse(self.gate.update(self.frame("hero_selection.png"), "HERO_SELECTION", 1))
        self.assertFalse(self.gate.update(self.frame("not_pregame.png"), "NOT_PREGAME", 2))
        self.assertTrue(self.gate.update(self.frame("competitive_pregame_tab.png"), "PREGAME", 3))

    def test_sustained_non_pregame_clears_evidence(self):
        self.gate.update(self.frame("competitive_pregame.png"), "PREGAME", 0)
        self.assertFalse(self.gate.update(self.frame("not_pregame.png"), "NOT_PREGAME", 1))
        self.assertFalse(self.gate.update(self.frame("not_pregame.png"), "NOT_PREGAME", 6))
        self.assertFalse(self.gate.update(self.frame("competitive_pregame_tab.png"), "PREGAME", 7))

    def test_return_after_long_transition_cannot_revive_evidence(self):
        self.gate.update(self.frame("competitive_pregame.png"), "PREGAME", 0)
        self.gate.update(self.frame("not_pregame.png"), "NOT_PREGAME", 1)
        self.assertFalse(self.gate.update(self.frame("competitive_pregame_tab.png"), "PREGAME", 6))
        self.assertTrue(self.gate.update(self.frame("competitive_pregame.png"), "PREGAME", 7))

    def test_pause_preserves_evidence_but_never_allows_recommendations(self):
        self.gate.update(self.frame("competitive_pregame.png"), "PREGAME", 0)
        self.assertFalse(self.gate.update(self.frame("pause_menu.png"), "PAUSE_MENU", 1))
        self.assertTrue(self.gate.update(self.frame("competitive_pregame_tab.png"), "PREGAME", 2))

    def test_evidence_expires_during_capture_gap(self):
        self.gate.update(self.frame("competitive_pregame.png"), "PREGAME", 0)
        self.assertFalse(self.gate.update(self.frame("competitive_pregame_tab.png"), "PREGAME", 90))

    def test_wrong_resolution_never_supplies_evidence(self):
        frame = np.zeros((1080, 1920, 3), np.uint8)
        self.assertFalse(self.gate.update(frame, "WRONG_RESOLUTION", 0))
        self.assertEqual(self.gate.marker_score(frame), 0)


if __name__ == "__main__":
    unittest.main()
