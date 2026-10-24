import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Starting settings, not statistically tuned values.
PRIOR_MATCHES = 500
MATCHUP_WEIGHT = 1.0
SYNERGY_WEIGHT = 1.0


def pair_adjustment(wins, matches, expected):
    """Return a baseline-adjusted effect, reduced for small samples."""
    observed = wins / matches
    reliability = matches / (matches + PRIOR_MATCHES)
    return (observed - expected) * reliability


class PickScorer:
    def __init__(self):
        self.hero_ids = json.loads(
            (ROOT / "hero_ids.json").read_text(encoding="utf-8")
        )
        cache = json.loads(
            (ROOT / "data" / "hero_stats.json").read_text(encoding="utf-8")
        )
        datasets = cache["datasets"]
        self.downloaded_at = cache["downloaded_at"]

        self.overall = {
            row["hero_id"]: row["wins"] / row["matches"]
            for row in datasets["overall"]
        }
        self.matchups = {
            (row["hero_id"], row["enemy_hero_id"]): row
            for row in datasets["matchups"]
        }
        self.synergies = {
            tuple(sorted((row["hero_id1"], row["hero_id2"]))): row
            for row in datasets["synergies"]
        }

    def score(self, hero, allies, enemies):
        """Allies must contain only the five OTHER teammates."""
        if len(allies) != 5 or len(enemies) != 6:
            raise ValueError("Provide five teammates and six enemies.")

        lineup = [hero, *allies, *enemies]
        if len(set(lineup)) != 12:
            raise ValueError("Heroes must be unique across both teams.")

        for name in lineup:
            if name not in self.hero_ids:
                raise ValueError(f"No hero ID for {name}")
            if self.hero_ids[name] not in self.overall:
                raise ValueError(f"No overall statistics for {name}")

        hero_id = self.hero_ids[hero]
        baseline = self.overall[hero_id]

        matchup_total = 0.0
        synergy_total = 0.0
        missing = []

        for enemy in enemies:
            enemy_id = self.hero_ids[enemy]
            row = self.matchups.get((hero_id, enemy_id))

            if row is None:
                missing.append(f"against {enemy}")
                continue

            # Approximate expectation from both heroes' overall strength.
            expected = 0.5 + baseline - self.overall[enemy_id]
            expected = max(0.0, min(1.0, expected))

            matchup_total += pair_adjustment(
                row["wins"], row["matches_played"], expected
            )

        for ally in allies:
            ally_id = self.hero_ids[ally]
            key = tuple(sorted((hero_id, ally_id)))
            row = self.synergies.get(key)

            if row is None:
                missing.append(f"with {ally}")
                continue

            expected = baseline + self.overall[ally_id] - 0.5
            expected = max(0.0, min(1.0, expected))

            synergy_total += pair_adjustment(
                row["wins"], row["matches_played"], expected
            )

        # Missing pairs contribute no adjustment, rather than a guessed rate.
        matchup_effect = matchup_total / len(enemies)
        synergy_effect = synergy_total / len(allies)

        score = 100 * (
            baseline
            + MATCHUP_WEIGHT * matchup_effect
            + SYNERGY_WEIGHT * synergy_effect
        )

        return {
            "hero": hero,
            "score": score,
            "baseline_pct": 100 * baseline,
            "matchup_points": 100 * MATCHUP_WEIGHT * matchup_effect,
            "synergy_points": 100 * SYNERGY_WEIGHT * synergy_effect,
            "missing": missing,
        }