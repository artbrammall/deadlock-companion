from scoring import PickScorer, pair_adjustment


def main():
    # Basic checks on the adjustment calculation.
    assert abs(pair_adjustment(50, 100, 0.5)) < 1e-12
    assert pair_adjustment(60, 100, 0.5) > 0
    assert pair_adjustment(40, 100, 0.5) < 0
    assert (
        pair_adjustment(6, 10, 0.5)
        < pair_adjustment(600, 1000, 0.5)
    )
    print("PASS: adjustment checks\n")

    scorer = PickScorer()

    # Your previous Silver lineup, excluding your own hero.
    allies = ["dynamo", "seven", "violet", "rat_king", "infernus"]
    enemies = [
        "grey_talon", "paige", "billy",
        "deadman_danny", "haze", "calico",
    ]

    # Small demonstration list, not your saved roster.
    candidates = ["silver", "apollo", "baba", "celeste"]

    results = [
        scorer.score(hero, allies, enemies)
        for hero in candidates
    ]
    results.sort(key=lambda result: (-result["score"], result["hero"]))

    print(f"Statistics downloaded: {scorer.downloaded_at}")
    print("Scores are ranking points, NOT win probabilities.\n")

    for result in results:
        print(
            f"{result['hero']:12} "
            f"score={result['score']:.2f} | "
            f"base={result['baseline_pct']:.2f} | "
            f"enemies={result['matchup_points']:+.2f} | "
            f"allies={result['synergy_points']:+.2f}"
        )
        if result["missing"]:
            print(f"  Missing data: {', '.join(result['missing'])}")


if __name__ == "__main__":
    main()