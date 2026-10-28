import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_paths import DATA_DIR
import argparse
import csv
import random
from collections import Counter
from pathlib import Path

from opportunity import OpportunityScorer
from pick_modes import choose_heroes
from recommendations import eligible_heroes
from roster import get_roster
from scoring import PickScorer

ROOT = Path(__file__).resolve().parents[1]
MODES = ("Best Opportunity", "Competitive", "Random")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=73421)
    args = parser.parse_args()

    if args.matches < 1:
        raise ValueError("Match count must be positive.")

    scorer = PickScorer()
    heroes = sorted(scorer.hero_ids)
    roster = sorted(set(get_roster()))

    if not roster:
        raise ValueError("Your saved roster is empty.")

    unknown = set(roster) - set(heroes)
    if unknown:
        raise ValueError(f"Unknown roster heroes: {sorted(unknown)}")

    if len(heroes) < 12:
        raise ValueError("Need at least 12 heroes.")

    opportunities = OpportunityScorer(scorer)

    # Separate generators keep lineup generation independent of random picks.
    lineup_rng = random.Random(args.seed)
    pick_rng = random.Random(args.seed + 1)

    eligible_counts = Counter()
    expected_random_first = Counter()
    expected_random_top3 = Counter()
    rank_counts = {
        mode: {hero: Counter() for hero in roster}
        for mode in MODES
    }

    for match_number in range(1, args.matches + 1):
        # Start on a uniformly chosen hero from your roster.
        current = lineup_rng.choice(roster)

        # Everyone else is drawn from the complete hero pool.
        others = lineup_rng.sample(
            [hero for hero in heroes if hero != current],
            11,
        )
        teammates = others[:5]
        enemies = others[5:]
        allies = [current, *teammates]

        choices = eligible_heroes(
            roster, allies, enemies, current
        )

        rows = []
        for hero in choices:
            result = scorer.score(hero, teammates, enemies)
            result.update(opportunities.describe(result))
            rows.append(result)

        count = len(rows)

        for hero in choices:
            eligible_counts[hero] += 1
            expected_random_first[hero] += 1 / count
            expected_random_top3[hero] += min(3, count) / count

        for mode in MODES:
            if mode == "Random":
                ranking = list(choices)
                pick_rng.shuffle(ranking)
            else:
                # Request the full ranking, rather than just three.
                ranking = choose_heroes(rows, mode, count=count)

            if len(ranking) != count or set(ranking) != set(choices):
                raise ValueError(f"{mode}: incomplete or invalid ranking")

            for position, hero in enumerate(ranking, start=1):
                rank_counts[mode][hero][position] += 1

        if match_number % 1000 == 0 or match_number == args.matches:
            print(
                f"Simulated {match_number:,}/{args.matches:,} lineups",
                flush=True,
            )

    # Check that the accumulated rankings account for every eligible pick.
    for mode in MODES:
        for hero in roster:
            if sum(rank_counts[mode][hero].values()) != eligible_counts[hero]:
                raise ValueError(f"Ranking count mismatch: {mode}/{hero}")

        first_places = sum(
            rank_counts[mode][hero][1] for hero in roster
        )
        if first_places != args.matches:
            raise ValueError(f"First-place count mismatch: {mode}")

    summary = []

    for mode in MODES:
        for hero in roster:
            eligible = eligible_counts[hero]
            positions = rank_counts[mode][hero]
            first = positions[1]
            top3 = sum(positions[position] for position in (1, 2, 3))

            summary.append({
                "mode": mode,
                "hero": hero,
                "simulated_matches": args.matches,
                "seed": args.seed,
                "stats_downloaded_at": scorer.downloaded_at,
                "eligible_count": eligible,
                "eligible_pct": 100 * eligible / args.matches,
                "first_count": first,
                "first_pct_when_eligible": (
                    100 * first / eligible if eligible else 0
                ),
                "top3_count": top3,
                "top3_pct_when_eligible": (
                    100 * top3 / eligible if eligible else 0
                ),
                "average_rank_when_eligible": (
                    sum(rank * total for rank, total in positions.items())
                    / eligible
                    if eligible else ""
                ),
                "random_expected_first_pct": (
                    100 * expected_random_first[hero] / eligible
                    if eligible else 0
                ),
                "random_expected_top3_pct": (
                    100 * expected_random_top3[hero] / eligible
                    if eligible else 0
                ),
            })

    output = DATA_DIR / "simulations"
    output.mkdir(parents=True, exist_ok=True)

    summary_path = output / "recommendation_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)

    ranks_path = output / "rank_counts.csv"
    with ranks_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["mode", "hero", "rank", "count"])

        for mode in MODES:
            for hero in roster:
                for rank in range(1, len(roster) + 1):
                    writer.writerow([
                        mode, hero, rank, rank_counts[mode][hero][rank]
                    ])

    print(f"\nStatistics: {scorer.downloaded_at}")
    print(f"Matches: {args.matches:,} | Seed: {args.seed}")
    print("All recommendation percentages below are WHEN ELIGIBLE.")

    for mode in MODES:
        print(f"\n{mode}")
        print(
            f"{'Hero':18} {'Eligible':>9} {'First%':>8} "
            f"{'Top3%':>8} {'Avg rank':>9} {'Random first%':>14}"
        )

        mode_rows = sorted(
            (row for row in summary if row["mode"] == mode),
            key=lambda row: (-row["first_pct_when_eligible"], row["hero"]),
        )

        for row in mode_rows:
            average = row["average_rank_when_eligible"]
            average_text = f"{average:.2f}" if average != "" else "N/A"

            print(
                f"{row['hero']:18} "
                f"{row['eligible_count']:9,d} "
                f"{row['first_pct_when_eligible']:8.2f} "
                f"{row['top3_pct_when_eligible']:8.2f} "
                f"{average_text:>9} "
                f"{row['random_expected_first_pct']:14.2f}"
            )

    print("\nPASS: ranking count checks")
    print(f"Saved {summary_path}")
    print(f"Saved {ranks_path}")


if __name__ == "__main__":
    main()