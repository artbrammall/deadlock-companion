import numpy as np


def detect_self(frame, layout):
    height, width = frame.shape[:2]

    if [width, height] != layout["resolution"]:
        return None

    scores = []

    for left, top, right, bottom in layout["ally_portraits"]:
        # Small patch near the portrait's upper-left corner.
        patch = frame[top + 2:top + 20, left + 2:left + 10]
        blue, green, red = np.median(
            patch.reshape(-1, 3), axis=0
        )

        blue_score = 0.0
        orange_score = 0.0

        if blue >= 145 and blue > green > red:
            blue_score = blue - red

        if red >= 150 and red > green > blue:
            orange_score = red - blue

        scores.append(max(blue_score, orange_score))

    order = np.argsort(scores)
    best = int(order[-1])
    runner_up = int(order[-2])

    # Provisional thresholds for your current UI settings.
    if scores[best] < 70:
        return None

    if scores[best] - scores[runner_up] < 25:
        return None

    return best