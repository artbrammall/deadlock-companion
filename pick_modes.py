import math
import random

MODES = ("Random", "Matchup variety", "Competitive")

# One point of matchup/synergy advantage multiplies the weighted
# portion of selection probability by approximately 2.7.
VARIETY_TEMPERATURE = 1.0


def selection_probabilities(rows, mode):
    if not rows:
        raise ValueError("No candidates available.")

    count = len(rows)

    if mode == "Random":
        return [1 / count] * count

    if mode == "Competitive":
        best = min(
            range(count),
            key=lambda index: (-rows[index]["score"], rows[index]["hero"]),
        )
        return [1.0 if index == best else 0.0 for index in range(count)]

    if mode != "Matchup variety":
        raise ValueError(f"Unknown selection mode: {mode}")

    # Overall win rate is deliberately excluded from this mode.
    effects = [
        row["matchup_points"] + row["synergy_points"]
        for row in rows
    ]

    highest = max(effects)
    weights = [
        math.exp((effect - highest) / VARIETY_TEMPERATURE)
        for effect in effects
    ]
    total = sum(weights)

    # Half uniform randomness, half matchup/synergy preference.
    return [
        0.5 / count + 0.5 * weight / total
        for weight in weights
    ]


def choose_heroes(rows, mode, count=3):
    if mode == "Competitive":
        ranked = sorted(
            rows,
            key=lambda row: (-row["score"], row["hero"]),
        )
        return [row["hero"] for row in ranked[:count]]

    remaining = list(rows)
    selected = []

    while remaining and len(selected) < count:
        probabilities = selection_probabilities(remaining, mode)

        index = random.choices(
            range(len(remaining)),
            weights=probabilities,
            k=1,
        )[0]

        selected.append(remaining.pop(index)["hero"])

    return selected