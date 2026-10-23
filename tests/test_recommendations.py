import unittest

from recommendations import eligible_heroes


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.allies = [
            "violet", "grey_talon", "mo_and_krill",
            "bebop", "calico", "silver",
        ]
        self.enemies = [
            "rem", "haze", "billy",
            "yamato", "dynamo", "deadman_danny",
        ]

    def test_excludes_taken_heroes_and_keeps_current(self):
        roster = ["violet", "haze", "bebop", "warden", "warden"]
        self.assertEqual(
            eligible_heroes(
                roster, self.allies, self.enemies, "violet"
            ),
            ["violet", "warden"],
        )

    def test_current_hero_need_not_be_in_roster(self):
        self.assertEqual(
            eligible_heroes(
                ["warden"], self.allies, self.enemies, "violet"
            ),
            ["violet", "warden"],
        )

    def test_unknown_identity_blocks_choices(self):
        self.assertEqual(
            eligible_heroes(
                ["warden"], self.allies, self.enemies, None
            ),
            [],
        )

    def test_unknown_portrait_blocks_choices(self):
        self.enemies[0] = "UNKNOWN"
        self.assertEqual(
            eligible_heroes(
                ["warden"], self.allies, self.enemies, "violet"
            ),
            [],
        )

    def test_duplicate_detection_blocks_choices(self):
        self.enemies[0] = self.allies[0]
        self.assertEqual(
            eligible_heroes(
                ["warden"], self.allies, self.enemies, "violet"
            ),
            [],
        )

    def test_partial_team_blocks_choices(self):
        self.assertEqual(
            eligible_heroes(
                ["warden"], self.allies[:2], self.enemies, "violet"
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()