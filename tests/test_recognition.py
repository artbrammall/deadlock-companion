import json
import unittest
from pathlib import Path

import cv2

from recognition import HeroRecognizer

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent


class RecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads(
            (ROOT / "screen_config.json").read_text(encoding="utf-8")
        )
        cls.cases = json.loads(
            (TESTS / "test_cases.json").read_text(encoding="utf-8")
        )
        if not cls.cases:
            raise ValueError("No test cases configured.")

        cls.layout = config["layouts"][config["active_layout"]]
        cls.recognizer = HeroRecognizer(ROOT / "portraits")

    def test_portraits(self):
        for filename, expected_teams in self.cases.items():
            with self.subTest(filename=filename):
                screenshot = cv2.imread(
                    str(TESTS / "samples" / filename)
                )
                self.assertIsNotNone(
                    screenshot, f"Cannot read sample: {filename}"
                )
                results = self.recognizer.recognize_teams(
                    screenshot, self.layout
                )

                for team in ("ally", "enemy"):
                    with self.subTest(team=team):
                        expected = expected_teams[team]
                        detected = results[team]
                        self.assertEqual(
                            len(expected),
                            len(detected),
                            f"{filename}: wrong number of {team} labels",
                        )

                        for slot, (wanted, result) in enumerate(
                            zip(expected, detected), start=1
                        ):
                            with self.subTest(slot=slot):
                                self.assertEqual(
                                    result["hero"],
                                    wanted,
                                    f"best={result['best_match']}, "
                                    f"score={result['score']:.3f}",
                                )


if __name__ == "__main__":
    unittest.main()