import json
import unittest
from pathlib import Path

import cv2
import numpy as np

from recognition import HeroRecognizer
from screen_state import ScreenStateDetector
from self_detection import detect_self
from ranked_gate import RankedPregameGate

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "tests" / "samples"


class RankedStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recognizer = HeroRecognizer(ROOT / "portraits")
        cls.layout = json.loads((ROOT / "screen_config.json").read_text())["layouts"]["ranked"]
        cls.state = ScreenStateDetector(ROOT / "screen_templates")

    def test_three_live_dropouts_recognise_all_twelve(self):
        allies = ["apollo", "venator", "dynamo", "rat_king", "the_doorman", "mirage"]
        enemies = ["haze", "billy", "violet", "celeste", "nurse_harrow", "deadman_danny"]
        for number in (1, 2, 3):
            with self.subTest(frame=number):
                frame = cv2.imread(str(SAMPLES / f"ranked_dropout_{number}.png"))
                self.assertIsNotNone(frame)
                results = self.recognizer.recognize_teams(frame, self.layout)
                wanted = enemies if number < 3 else [
                    "nurse_harrow", "billy", "violet", "celeste", "haze", "deadman_danny"
                ]
                self.assertEqual([r["hero"] for r in results["ally"]], allies)
                self.assertEqual([r["hero"] for r in results["enemy"]], wanted)
                self.assertEqual(self.state.detect(frame)[0], "PREGAME")
                self.assertEqual(detect_self(frame, self.layout), 5)
                gate = RankedPregameGate(ROOT / "screen_templates")
                self.assertTrue(gate.update(frame, "PREGAME", 0))

    def test_regions_reject_blank_and_random_noise(self):
        rng = np.random.default_rng(719)
        frames = [np.full((88, 74, 3), v, np.uint8) for v in (0, 80, 255)]
        frames += [rng.integers(0, 256, (88, 74, 3), dtype=np.uint8) for _ in range(50)]
        for first in (False, True):
            for i, frame in enumerate(frames):
                with self.subTest(first=first, image=i):
                    self.assertEqual(
                        self.recognizer.recognize_regions(frame, first)["hero"], "UNKNOWN"
                    )

    def test_one_matching_fragment_is_insufficient(self):
        rng = np.random.default_rng(13)
        reference = cv2.imread(str(ROOT / "portraits" / "haze.png"))
        self.assertIsNotNone(reference)
        reference = cv2.resize(reference, (74, 88))
        image = rng.integers(0, 256, (88, 74, 3), dtype=np.uint8)
        image[8:36, 12:40] = reference[8:36, 12:40]
        for first in (False, True):
            self.assertEqual(self.recognizer.recognize_regions(image, first)["hero"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
