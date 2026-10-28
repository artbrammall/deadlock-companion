import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_paths import DATA_DIR
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_counts(row, matches_field, label):
    wins = row["wins"]
    matches = row[matches_field]

    require(
        type(wins) is int and type(matches) is int,
        f"{label}: counts must be integers",
    )
    require(
        matches > 0 and 0 <= wins <= matches,
        f"{label}: invalid wins/matches: {wins}/{matches}",
    )


def main():
    mapping = json.loads(
        (ROOT / "hero_ids.json").read_text(encoding="utf-8")
    )
    cache = json.loads(
        (DATA_DIR / "hero_stats.json").read_text(encoding="utf-8")
    )
    datasets = cache["datasets"]

    require(bool(mapping), "Hero mapping is empty")
    require(
        all(type(value) is int for value in mapping.values()),
        "Hero IDs must be integers",
    )

    hero_ids = set(mapping.values())
    require(len(hero_ids) == len(mapping), "Duplicate IDs in hero mapping")

    # Check each hero's overall statistics.
    overall_ids = set()
    for row in datasets["overall"]:
        hero_id = row["hero_id"]
        require(hero_id in hero_ids, f"Unknown hero ID: {hero_id}")
        require(hero_id not in overall_ids, f"Duplicate overall ID: {hero_id}")
        check_counts(row, "matches", f"Hero {hero_id}")

        require(
            type(row["losses"]) is int and row["losses"] >= 0,
            f"Hero {hero_id}: invalid losses",
        )
        require(
            row["wins"] + row["losses"] == row["matches"],
            f"Hero {hero_id}: wins + losses != matches",
        )
        overall_ids.add(hero_id)

    require(overall_ids == hero_ids, "Missing overall hero statistics")
    print(f"PASS: {len(overall_ids)} overall hero records")

    # Enemy pairs are directional; allied pairs are unordered.
    pair_types = [
        ("matchups", "hero_id", "enemy_hero_id", False),
        ("synergies", "hero_id1", "hero_id2", True),
    ]

    for name, first_field, second_field, unordered in pair_types:
        seen = set()

        for row in datasets[name]:
            first = row[first_field]
            second = row[second_field]
            label = f"{name}: {first}, {second}"

            require(
                first in hero_ids and second in hero_ids,
                f"{label}: unknown hero ID",
            )
            require(first != second, f"{label}: hero paired with itself")
            check_counts(row, "matches_played", label)

            pair = tuple(sorted((first, second))) if unordered else (first, second)
            require(pair not in seen, f"{label}: duplicate pair")
            seen.add(pair)

        require(bool(seen), f"{name}: dataset is empty")

        expected = len(hero_ids) * (len(hero_ids) - 1)
        if unordered:
            expected //= 2

        missing = expected - len(seen)
        print(f"PASS: {len(seen)} valid {name} records")

        if missing:
            print(
                f"WARNING: {missing} missing {name} pairs. "
                "Treat these as unavailable, not zero wins."
            )
        else:
            print(f"PASS: complete {name} coverage")

    print("\nValidation passed.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"\nFAIL: {error}")
        raise SystemExit(1)