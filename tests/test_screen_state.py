import unittest
from pathlib import Path

import cv2
import numpy as np

from screen_state import ScreenStateDetector

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "tests" / "samples"

CASES = {
    "010.png": "PREGAME",
    "012.png": "PREGAME",
    "match2_normal.png": "PREGAME",
    "match2_tab.png": "PREGAME",
    "001.png": "NOT_PREGAME",
    "002.png": "NOT_PREGAME",
    "003.png": "NOT_PREGAME",
    "005.png": "NOT_PREGAME",
    "not_pregame.png": "NOT_PREGAME",
    "pause_menu.png": "PAUSE_MENU",
    "hero_selection.png": "HERO_SELECTION",
    "pregame_character.png": "LOADING",
}


class ScreenStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = ScreenStateDetector(ROOT / "screen_templates")

    def check_state(self, frame, expected):
        actual, scores = self.detector.detect(frame)
        self.assertEqual(actual, expected, f"Scores: {scores}")

    def test_saved_screenshots(self):
        for filename, expected in CASES.items():
            with self.subTest(filename=filename):
                image = cv2.imread(str(SAMPLES / filename))
                self.assertIsNotNone(
                    image, f"Cannot read sample: {filename}"
                )
                self.check_state(image, expected)

    def test_black_frame(self):
        self.check_state(
            np.zeros((990, 1760, 3), dtype=np.uint8),
            "NOT_PREGAME",
        )

    def test_wrong_resolution(self):
        self.check_state(
            np.zeros((1080, 1920, 3), dtype=np.uint8),
            "WRONG_RESOLUTION",
        )


if __name__ == "__main__":
    unittest.main()