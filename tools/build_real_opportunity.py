import hashlib
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from scoring import (
    PickScorer,
    PRIOR_MATCHES,
    MATCHUP_WEIGHT,
    SYNERGY_WEIGHT,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = 29173


def main():
    stats_path = ROOT / "data" / "hero_stats.json"
    source_path = ROOT / "data" / "real_lineups.json"

    stats_bytes = stats_path.read_bytes()
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    stats = json.loads(stats_bytes)

    # Keep the source period consistent for this experiment.
    if source["filters"] != stats["filters"]:
        raise ValueError(
            "Statistics and lineups use different filters. "
            "Use matching snapshots before building the reference."
        )

    scorer = PickScorer()
    id_to_name = {
        hero_id: name for name, hero_id in scorer.hero_ids.items()
    }

    lineups = sorted(source["lineups"], key=lambda row: row["match_id"])
    seen = set()

    for match in lineups:
        match_id = match["match_id"]
        if match_id in seen:
            raise ValueError(f"Duplicate match: {match_id}")
        seen.add(match_id)

        team0 = match["team0"]
        team1 = match["team1"]
        heroes = team0 + team1

        if len(team0) != 6 or len(team1) != 6 or len(set(heroes)) != 12:
            raise ValueError(f"Invalid lineup: {match_id}")

        if not set(heroes) <= id_to_name.keys():
            raise ValueError(f"Unknown hero in match: {match_id}")

    if len(lineups) < 2:
        raise ValueError("Need at least two matches.")

    # Split whole matches, never individual players.
    random.Random(SEED).shuffle(lineups)
    test_count = max(1, len(lineups) // 5)
    test_matches = lineups[:test_count]
    reference_matches = lineups[test_count:]

    reference_ids = {match["match_id"] for match in reference_matches}
    test_ids = {match["match_id"] for match in test_matches}

    if reference_ids & test_ids:
        raise ValueError("Reference and test matches overlap.")

    effects = {hero: [] for hero in scorer.hero_ids}
    test_appearances = Counter()

    for match in test_matches:
        for hero_id in match["team0"] + match["team1"]:
            test_appearances[id_to_name[hero_id]] += 1

    for index, match in enumerate(reference_matches, 1):
        team0 = [id_to_name[value] for value in match["team0"]]
        team1 = [id_to_name[value] for value in match["team1"]]

        for allies, enemies in ((team0, team1), (team1, team0)):
            for hero in allies:
                teammates = [ally for ally in allies if ally != hero]
                result = scorer.score(hero, teammates, enemies)

                if result["missing"]:
                    raise ValueError(
                        f"{hero}: missing pair statistics "
                        f"in match {match['match_id']}"
                    )

                effect = (
                    result["matchup_points"] + result["synergy_points"]
                )
                effects[hero].append(effect)

        if index % 1000 == 0:
            print(
                f"Processed {index:,}/{len(reference_matches):,} "
                "reference matches",
                flush=True,
            )

    references = {}

    for hero, values in sorted(effects.items()):
        if not values:
            raise ValueError(f"No reference situations for {hero}")

        references[hero] = {
            "count": len(values),
            "mean_adjustment": mean(values),
            "sorted_adjustments": sorted(
                round(value, 8) for value in values
            ),
        }

    experiment = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "filters": source["filters"],
        "stats_sha256": hashlib.sha256(stats_bytes).hexdigest(),
        "lineups_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "scoring_settings": {
            "prior_matches": PRIOR_MATCHES,
            "matchup_weight": MATCHUP_WEIGHT,
            "synergy_weight": SYNERGY_WEIGHT,
        },
        "reference_match_ids": sorted(reference_ids),
        "references": references,
        "test_lineups": sorted(
            test_matches, key=lambda row: row["match_id"]
        ),
    }

    output = ROOT / "data" / "real_opportunity_experiment.json"
    temporary = output.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(experiment, indent=2),
        encoding="utf-8",
    )
    temporary.replace(output)

    print(f"\nReference matches: {len(reference_matches):,}")
    print(f"Test matches:      {len(test_matches):,}")
    print("PASS: no match appears in both sets")

    print(f"\n{'Hero':18} {'Reference':>10} {'Test':>8}")
    for hero in sorted(references):
        print(
            f"{hero:18} "
            f"{references[hero]['count']:10,d} "
            f"{test_appearances[hero]:8,d}"
        )

    print(f"\nSaved {output}")


if __name__ == "__main__":
    main()