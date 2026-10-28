import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_paths import DATA_DIR
import hashlib
import json
from bisect import bisect_left, bisect_right
from pathlib import Path
from statistics import mean

from scoring import (
    PickScorer,
    PRIOR_MATCHES,
    MATCHUP_WEIGHT,
    SYNERGY_WEIGHT,
)

ROOT = Path(__file__).resolve().parents[1]


def percentile(values, effect):
    rounded = round(effect, 8)
    below = bisect_left(values, rounded)
    below_or_equal = bisect_right(values, rounded)
    return 100 * (below + below_or_equal) / (2 * len(values))


def main():
    experiment = json.loads(
        (DATA_DIR / "real_opportunity_experiment.json").read_text(
            encoding="utf-8"
        )
    )
    stats_bytes = (DATA_DIR / "hero_stats.json").read_bytes()

    if hashlib.sha256(stats_bytes).hexdigest() != experiment["stats_sha256"]:
        raise ValueError("Statistics changed. Use the experiment's snapshot.")

    settings = {
        "prior_matches": PRIOR_MATCHES,
        "matchup_weight": MATCHUP_WEIGHT,
        "synergy_weight": SYNERGY_WEIGHT,
    }
    if settings != experiment["scoring_settings"]:
        raise ValueError("Scoring settings changed. Rebuild the experiment.")

    scorer = PickScorer()
    names = {
        hero_id: name for name, hero_id in scorer.hero_ids.items()
    }
    references = experiment["references"]
    results = {hero: [] for hero in scorer.hero_ids}

    reference_ids = set(experiment["reference_match_ids"])
    seen_test_ids = set()

    for match in experiment["test_lineups"]:
        match_id = match["match_id"]

        if match_id in reference_ids or match_id in seen_test_ids:
            raise ValueError("Overlapping or duplicate test match.")
        seen_test_ids.add(match_id)

        team0 = [names[value] for value in match["team0"]]
        team1 = [names[value] for value in match["team1"]]

        for allies, enemies in ((team0, team1), (team1, team0)):
            for hero in allies:
                teammates = [ally for ally in allies if ally != hero]
                result = scorer.score(hero, teammates, enemies)

                if result["missing"]:
                    raise ValueError(f"Missing pair statistics for {hero}")

                effect = (
                    result["matchup_points"] + result["synergy_points"]
                )
                values = references[hero]["sorted_adjustments"]

                if not values:
                    raise ValueError(f"Empty reference for {hero}")

                results[hero].append(percentile(values, effect))

    print(f"Checked {len(seen_test_ids):,} distinct test matches.")
    print("Only the heroes actually played are evaluated.")
    print("Targets are approximate, not pass/fail thresholds.\n")

    print(
        f"{'Hero':18} {'Ref N':>7} {'Test N':>7} "
        f"{'Mean pctile':>12} {'Below 50%':>10} {'At/above 90%':>13}"
    )

    report = []

    for hero in sorted(results):
        values = results[hero]
        if not values:
            print(f"{hero:18} No test appearances")
            continue

        below50 = 100 * sum(value < 50 for value in values) / len(values)
        above90 = 100 * sum(value >= 90 for value in values) / len(values)

        row = {
            "hero": hero,
            "reference_count": references[hero]["count"],
            "test_count": len(values),
            "mean_percentile": mean(values),
            "below_50_pct": below50,
            "at_or_above_90_pct": above90,
        }
        report.append(row)

        print(
            f"{hero:18} {row['reference_count']:7,d} "
            f"{row['test_count']:7,d} "
            f"{row['mean_percentile']:12.1f} "
            f"{below50:10.1f} {above90:13.1f}"
        )

    output = DATA_DIR / "opportunity_calibration.json"
    output.write_text(
        json.dumps({
            "stats_sha256": experiment["stats_sha256"],
            "test_matches": len(seen_test_ids),
            "results": report,
        }, indent=2),
        encoding="utf-8",
    )

    print("\nApproximate targets: mean percentile 50; below 50: 50%; top tail: 10%.")
    print(f"Saved {output}")


if __name__ == "__main__":
    main()