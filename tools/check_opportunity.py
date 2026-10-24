import random
from bisect import bisect_left, bisect_right
from statistics import mean, pstdev

from scoring import PickScorer

SIMULATIONS = 10_000
SEED = 2026


def adjustment(result):
    return result["matchup_points"] + result["synergy_points"]


def percentile(distribution, value):
    # Round away insignificant floating-point differences.
    values = sorted(round(item, 8) for item in distribution)
    value = round(value, 8)

    below = bisect_left(values, value)
    below_or_equal = bisect_right(values, value)

    # Tied results share the middle rank.
    return 100 * (below + below_or_equal) / (2 * len(values))


def comparison_pool(scorer, hero):
    hero_id = scorer.hero_ids[hero]
    pool = []

    for other in sorted(scorer.hero_ids):
        if other == hero:
            continue

        other_id = scorer.hero_ids[other]
        if other_id not in scorer.overall:
            raise ValueError(f"Missing overall statistics for {other}")

        if (hero_id, other_id) not in scorer.matchups:
            raise ValueError(f"Missing matchup: {hero} against {other}")

        key = tuple(sorted((hero_id, other_id)))
        if key not in scorer.synergies:
            raise ValueError(f"Missing synergy: {hero} with {other}")

        pool.append(other)

    if len(pool) < 11:
        raise ValueError("Not enough heroes to generate a complete lineup.")

    return pool


def pair_counts(scorer, hero, allies, enemies):
    hero_id = scorer.hero_ids[hero]

    enemy_counts = [
        scorer.matchups[
            (hero_id, scorer.hero_ids[enemy])
        ]["matches_played"]
        for enemy in enemies
    ]

    ally_counts = [
        scorer.synergies[
            tuple(sorted((hero_id, scorer.hero_ids[ally])))
        ]["matches_played"]
        for ally in allies
    ]

    return enemy_counts + ally_counts


def evaluate(scorer, hero, allies, enemies):
    actual = scorer.score(hero, allies, enemies)

    if actual["missing"]:
        raise ValueError(f"{hero}: actual lineup has missing pair data")

    pool = comparison_pool(scorer, hero)

    # A fixed seed makes reruns reproducible with the same statistics.
    rng = random.Random(f"{SEED}:{hero}")
    distribution = []

    for _ in range(SIMULATIONS):
        # Sample without replacement: no duplicate heroes.
        lineup = rng.sample(pool, 11)
        simulated = scorer.score(hero, lineup[:5], lineup[5:])
        distribution.append(adjustment(simulated))

    actual_effect = adjustment(actual)
    typical_effect = mean(distribution)
    spread = pstdev(distribution)
    counts = pair_counts(scorer, hero, allies, enemies)

    return {
        "hero": hero,
        "percentile": percentile(distribution, actual_effect),
        "effect": actual_effect,
        "typical": typical_effect,
        "above_typical": actual_effect - typical_effect,
        "spread": spread,
        "score": actual["score"],
        "baseline": actual["baseline_pct"],
        "min_pair_matches": min(counts),
        "max_pair_matches": max(counts),
    }


def main():
    # Check percentile boundaries and tied results.
    assert percentile([1, 2, 3], 0) == 0
    assert percentile([1, 2, 3], 4) == 100
    assert percentile([2, 2, 2], 2) == 50
    print("PASS: percentile checks\n")

    scorer = PickScorer()

    # Same example as check_scores.py.
    allies = ["dynamo", "seven", "violet", "rat_king", "infernus"]
    enemies = [
        "grey_talon", "paige", "billy",
        "deadman_danny", "haze", "calico",
    ]
    candidates = ["silver", "apollo", "baba", "celeste"]

    results = []

    for hero in candidates:
        print(f"Evaluating {hero} against {SIMULATIONS:,} lineups...", flush=True)

        # Lane order must not affect our opportunity measurement.
        normal = scorer.score(hero, allies, enemies)
        reordered = scorer.score(hero, allies[::-1], enemies[::-1])
        assert abs(adjustment(normal) - adjustment(reordered)) < 1e-9

        results.append(evaluate(scorer, hero, allies, enemies))

    results.sort(key=lambda result: (-result["percentile"], result["hero"]))

    print(f"\nStatistics downloaded: {scorer.downloaded_at}")
    print("Reference: uniformly sampled legal 6v6 hero compositions.")
    print("Opportunity percentiles are NOT win probabilities.\n")

    for result in results:
        print(
            f"{result['hero']}: "
            f"{result['percentile']:.1f}th-percentile opportunity"
        )
        print(
            f"  Lineup adjustment: {result['effect']:+.3f} points"
            f" | Typical: {result['typical']:+.3f}"
            f" | Above typical: {result['above_typical']:+.3f}"
        )
        print(
            f"  Simulated spread: {result['spread']:.3f} points"
            f" | Overall win rate: {result['baseline']:.2f}%"
            f" | Competitive score: {result['score']:.2f}"
        )
        print(
            "  Matches supporting individual pairs: "
            f"{result['min_pair_matches']:,}–"
            f"{result['max_pair_matches']:,}\n"
        )


if __name__ == "__main__":
    main()