import json
import unittest
from pathlib import Path
import cv2
from recognition import HeroRecognizer, rank_hero_matches

ROOT = Path(__file__).resolve().parent.parent


class PortraitVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recognizer = HeroRecognizer(ROOT / "portraits")
        cls.layout = json.loads((ROOT / "screen_config.json").read_text())["layouts"]["ranked"]

    def test_both_danny_directions_map_to_one_hero(self):
        for path in (ROOT / "portraits/deadman_danny.png",
                     ROOT / "portraits/variants/deadman_danny/mirrored.png"):
            image = cv2.imread(str(path))
            self.assertIsNotNone(image)
            with self.subTest(path=path.name):
                self.assertEqual(self.recognizer.recognize(image)["hero"], "deadman_danny")
                self.assertEqual(self.recognizer.recognize_faded(image)["hero"], "deadman_danny")
                self.assertEqual(self.recognizer.recognize_regions(image)["hero"], "deadman_danny")

    def test_margin_compares_distinct_heroes(self):
        self.assertEqual(rank_hero_matches([
            (0.99, "deadman_danny"), (0.98, "deadman_danny__mirrored"),
            (0.30, "yamato"),
        ]), [(0.99, "deadman_danny"), (0.30, "yamato")])

    def test_support_belongs_to_winning_reference(self):
        self.assertEqual(rank_hero_matches([
            (0.80, "deadman_danny", False),
            (0.96, "deadman_danny__mirrored", True),
            (0.40, "yamato", False),
        ])[0], (0.96, "deadman_danny", True))

    def test_new_match_lineups(self):
        cases = {
            "portrait_update_blue.png": (
                ["infernus", "nurse_harrow", "rat_king", "haze", "mo_and_krill", "deadman_danny"],
                ["yamato", "mcginnis", "bebop", "silver", "grey_talon", "violet"]),
            "portrait_update_orange.png": (
                ["venator", "pocket", "deadman_danny", "rem", "violet", "mo_and_krill"],
                ["bebop", "mina", "silver", "paige", "lash", "rat_king"]),
        }
        for filename, (allies, enemies) in cases.items():
            with self.subTest(filename=filename):
                frame = cv2.imread(str(ROOT / "tests/samples/portrait_variants" / filename))
                self.assertIsNotNone(frame)
                result = self.recognizer.recognize_teams(frame, self.layout)
                self.assertEqual([r["hero"] for r in result["ally"]], allies)
                self.assertEqual([r["hero"] for r in result["enemy"]], enemies)


if __name__ == "__main__":
    unittest.main()
