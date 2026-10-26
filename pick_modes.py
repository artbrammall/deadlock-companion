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


# Preference weights, not fitted estimates of win probability.
COMPETITIVE_BALANCE_POINTS = 2.0
OPPORTUNITY_BALANCE_POINTS = 10.0


def balance_adjustments(rows, mode, counts):
    usable = [r for r in rows if mode != 'Best Opportunity'
              or 'opportunity_percentile' in r]
    if not usable:
        return {}
    highest = max(counts.get(r['hero'], 0) for r in usable)
    scale = (COMPETITIVE_BALANCE_POINTS if mode == 'Competitive'
             else OPPORTUNITY_BALANCE_POINTS)
    return {r['hero']: scale * (highest - counts.get(r['hero'], 0))
            for r in usable}


def choose_balanced(rows, mode, counts, count=3, rng=None):
    if mode not in MODES:
        raise ValueError(f'Unknown mode: {mode}')
    if mode == 'Random':
        rng = rng or random
        remaining = list(rows)
        chosen = []
        minimum = min((counts.get(r['hero'], 0) for r in remaining), default=0)
        for _ in range(min(count, len(remaining))):
            weights = [1 / (1 + counts.get(r['hero'], 0) - minimum) for r in remaining]
            row = rng.choices(remaining, weights=weights, k=1)[0]
            chosen.append(row['hero'])
            remaining.remove(row)
        return chosen
    bonuses = balance_adjustments(rows, mode, counts)
    usable = [r for r in rows if r['hero'] in bonuses]
    field = 'score' if mode == 'Competitive' else 'opportunity_percentile'
    ranked = sorted(usable, key=lambda r: (
        -(r[field] + bonuses[r['hero']]),
        -r[field],
        -r.get('above_typical_points', 0) if mode == 'Best Opportunity' else 0,
        r['hero'],
    ))
    return [r['hero'] for r in ranked[:count]]
