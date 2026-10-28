import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_paths import DATA_DIR
import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import Counter
from pathlib import Path

from opportunity import OpportunityScorer
from recommendations import eligible_heroes
from roster import get_roster
from scoring import (
    PickScorer,
    PRIOR_MATCHES,
    MATCHUP_WEIGHT,
    SYNERGY_WEIGHT,
)

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("Uniform reference", "Real reference", "Competitive")


def percentile(values, effect):
    effect = round(effect, 8)
    below = bisect_left(values, effect)
    below_or_equal = bisect_right(values, effect)
    return 100 * (below + below_or_equal) / (2 * len(values))


def main():
    experiment = json.loads(
        (DATA_DIR / "real_opportunity_experiment.json").read_text(
            encoding="utf-8"
        )
    )
    stats_bytes = (DATA_DIR / "hero_stats.json").read_bytes()

    if hashlib.sha256(stats_bytes).hexdigest() != experiment["stats_sha256"]:
        raise ValueError(
            "Statistics changed. Rebuild the experiment using matching data."
        )

    settings = {
        "prior_matches": PRIOR_MATCHES,
        "matchup_weight": MATCHUP_WEIGHT,
        "synergy_weight": SYNERGY_WEIGHT,
    }
    if settings != experiment["scoring_settings"]:
        raise ValueError("Scoring settings changed. Rebuild the experiment.")

    scorer = PickScorer()
    roster = sorted(set(get_roster()))
    if not roster or not set(roster) <= scorer.hero_ids.keys():
        raise ValueError("Roster is empty or contains unknown heroes.")

    id_to_name = {
        hero_id: name for name, hero_id in scorer.hero_ids.items()
    }
    references = experiment["references"]
    uniform = OpportunityScorer(scorer)

    eligible_counts = Counter()
    random_expected = Counter()
    counts = {
        method: {hero: Counter() for hero in roster}
        for method in METHODS
    }

    scenarios = 0
    contributing_matches = 0

    for match_number, match in enumerate(experiment["test_lineups"], 1):
        team0 = [id_to_name[value] for value in match["team0"]]
        team1 = [id_to_name[value] for value in match["team1"]]
        contributed = False

        for allies, enemies in ((team0, team1), (team1, team0)):
            for current in allies:
                if current not in roster:
                    continue

                contributed = True
                scenarios += 1
                teammates = [hero for hero in allies if hero != current]
                choices = eligible_heroes(roster, allies, enemies, current)

                rows = []
                for hero in choices:
                    result = scorer.score(hero, teammates, enemies)
                    if result["missing"]:
                        raise ValueError(f"Missing pair data for {hero}")

                    effect = (
                        result["matchup_points"] + result["synergy_points"]
                    )
                    reference = references[hero]

                    result["uniform_percentile"] = uniform.describe(
                        result
                    )["opportunity_percentile"]
                    result["real_percentile"] = percentile(
                        reference["sorted_adjustments"], effect
                    )
                    result["uniform_above"] = effect - uniform.averages[hero]
                    result["real_above"] = (
                        effect - reference["mean_adjustment"]
                    )
                    rows.append(result)

                for hero in choices:
                    eligible_counts[hero] += 1
                    random_expected[hero] += 1 / len(choices)

                rankings = {
                    "Uniform reference": sorted(
                        rows,
                        key=lambda row: (
                            -row["uniform_percentile"],
                            -row["uniform_above"],
                            row["hero"],
                        ),
                    ),
                    "Real reference": sorted(
                        rows,
                        key=lambda row: (
                            -row["real_percentile"],
                            -row["real_above"],
                            row["hero"],
                        ),
                    ),
                    "Competitive": sorted(
                        rows,
                        key=lambda row: (-row["score"], row["hero"]),
                    ),
                }

                for method, ranking in rankings.items():
                    for rank, row in enumerate(ranking, 1):
                        counts[method][row["hero"]][rank] += 1

        contributing_matches += int(contributed)

        if match_number % 250 == 0:
            print(
                f"Replayed {match_number:,} test matches",
                flush=True,
            )

    if scenarios == 0:
        raise ValueError("No roster-held positions found in test matches.")

    print(
        f"\n{scenarios:,} decision scenarios from "
        f"{contributing_matches:,} distinct matches."
    )
    print("Uses visible-lineup eligibility; bans are not applied in this test.")
    print("First% and Top3% are percentages WHEN ELIGIBLE.")

    for method in METHODS:
        total_first = sum(counts[method][hero][1] for hero in roster)
        if total_first != scenarios:
            raise ValueError(f"{method}: first-place count mismatch")

        print(f"\n{method}")
        print(
            f"{'Hero':18} {'Eligible':>9} {'First%':>8} "
            f"{'Top3%':>8} {'Avg rank':>9} {'Random first%':>14}"
        )

        for hero in sorted(
            roster,
            key=lambda name: (
                -counts[method][name][1] / max(1, eligible_counts[name]),
                name,
            ),
        ):
            eligible = eligible_counts[hero]
            positions = counts[method][hero]

            if sum(positions.values()) != eligible:
                raise ValueError(f"{method}/{hero}: ranking count mismatch")

            if eligible == 0:
                print(f"{hero:18}         0      N/A      N/A       N/A")
                continue

            first_pct = 100 * positions[1] / eligible
            top3_pct = 100 * sum(positions[r] for r in (1, 2, 3)) / eligible
            average = sum(r * n for r, n in positions.items()) / eligible
            random_pct = 100 * random_expected[hero] / eligible

            print(
                f"{hero:18} {eligible:9,d} {first_pct:8.2f} "
                f"{top3_pct:8.2f} {average:9.2f} {random_pct:14.2f}"
            )

    print("\nPASS: ranking count checks")


if __name__ == "__main__":
    main()