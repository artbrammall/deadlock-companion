import random
from bisect import bisect_left, bisect_right
from statistics import mean

SIMULATIONS = 10_000
SEED = 2026


class OpportunityScorer:
    def __init__(self, scorer):
        self.distributions = {}
        self.averages = {}

        heroes = sorted(scorer.hero_ids)

        # Require complete reference data for this initial implementation.
        for hero in heroes:
            hero_id = scorer.hero_ids[hero]

            if hero_id not in scorer.overall:
                raise ValueError(f"Missing overall statistics: {hero}")

            for other in heroes:
                if other == hero:
                    continue

                other_id = scorer.hero_ids[other]
                if (hero_id, other_id) not in scorer.matchups:
                    raise ValueError(f"Missing matchup: {hero}/{other}")

                key = tuple(sorted((hero_id, other_id)))
                if key not in scorer.synergies:
                    raise ValueError(f"Missing synergy: {hero}/{other}")

        for position, hero in enumerate(heroes, start=1):
            print(
                f"Preparing opportunities: {hero} "
                f"({position}/{len(heroes)})",
                flush=True,
            )

            pool = [other for other in heroes if other != hero]
            rng = random.Random(f"{SEED}:{hero}")
            effects = []

            for _ in range(SIMULATIONS):
                lineup = rng.sample(pool, 11)
                result = scorer.score(hero, lineup[:5], lineup[5:])
                effects.append(
                    result["matchup_points"] + result["synergy_points"]
                )

            self.averages[hero] = mean(effects)
            self.distributions[hero] = sorted(
                round(effect, 8) for effect in effects
            )

    def describe(self, result):
        hero = result["hero"]
        effect = result["matchup_points"] + result["synergy_points"]
        values = self.distributions[hero]
        rounded = round(effect, 8)

        below = bisect_left(values, rounded)
        below_or_equal = bisect_right(values, rounded)
        percentile = 100 * (below + below_or_equal) / (2 * len(values))

        return {
            "opportunity_percentile": percentile,
            "above_typical_points": effect - self.averages[hero],
        }