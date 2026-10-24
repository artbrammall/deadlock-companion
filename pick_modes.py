import random

MODES = ("Random", "Best Opportunity", "Competitive")

def selection_probabilities(rows, mode):
    if not rows:
        raise ValueError("No candidates available.")

    if mode == "Random":
        return [1 / len(rows)] * len(rows)

    raise ValueError("Only Random mode uses selection probabilities.")


def choose_heroes(rows, mode, count=3):
    if mode == "Random":
        return random.sample(
            [row["hero"] for row in rows],
            k=min(count, len(rows)),
        )

    if mode == "Competitive":
        ranked = sorted(
            rows,
            key=lambda row: (-row["score"], row["hero"]),
        )

    elif mode == "Best Opportunity":
        usable = [
            row for row in rows
            if "opportunity_percentile" in row
        ]

        ranked = sorted(
            usable,
            key=lambda row: (
                -row["opportunity_percentile"],
                -row["above_typical_points"],
                row["hero"],
            ),
        )

    else:
        raise ValueError(f"Unknown mode: {mode}")

    return [row["hero"] for row in ranked[:count]]