import json
import unittest
from pathlib import Path

import cv2
import numpy as np

from self_detection import detect_self

ROOT = Path(__file__).resolve().parent.parent

# Expected slots use human-readable numbering: 1 to 6.
CASES = {
    "009.png": 5,
    "010.png": 1,
    "012.png": 1,
    "001.png": 6,
    "match2_normal.png": 1,
    "match2_tab.png": 3,
}


class SelfDetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads(
            (ROOT / "screen_config.json").read_text(encoding="utf-8")
        )
        cls.layout = config["layouts"][config["active_layout"]]

    def test_saved_screenshots(self):
        for filename, expected in CASES.items():
            with self.subTest(filename=filename):
                image = cv2.imread(
                    str(ROOT / "tests" / "samples" / filename)
                )
                self.assertIsNotNone(
                    image, f"Cannot read sample: {filename}"
                )

                slot = detect_self(image, self.layout)
                actual = None if slot is None else slot + 1
                self.assertEqual(actual, expected)

    def test_blank_screen(self):
        blank = np.zeros((990, 1760, 3), dtype=np.uint8)
        self.assertIsNone(detect_self(blank, self.layout))


if __name__ == "__main__":
    unittest.main()