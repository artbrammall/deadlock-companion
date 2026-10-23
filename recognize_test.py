from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent

# Starting values only; we will tune these using more screenshots.
MIN_SCORE = 0.75
MIN_MARGIN = 0.08


def prepare(path, search=False):
    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"Cannot read: {path}")

    image = cv2.resize(image, (74, 88))

    if search:
        # Search within three pixels of the expected position.
        image = image[5:73, 9:65]
    else:
        # Reference portrait stays the original size.
        image = image[8:70, 12:62]

    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


references = {
    path.stem: prepare(path)
    for path in sorted((ROOT / "portraits").glob("*.png"))
}

if len(references) < 2:
    raise RuntimeError("Add labelled hero PNGs to the portraits folder.")

# Test different screenshots from the one used for references.
for screenshot in ["009", "010", "012", "001"]:
    print(f"\n--- Screenshot {screenshot} ---")

    for team in ["ally", "enemy"]:
        for slot in range(1, 7):
            path = ROOT / "debug_crops" / screenshot / f"{team}_{slot}.png"
            portrait = prepare(path, search=True)

            matches = []
            for hero, reference in references.items():
                score = float(cv2.matchTemplate(
                    portrait, reference, cv2.TM_CCOEFF_NORMED
                ).max())

                if not np.isfinite(score):
                    score = -1.0

                matches.append((score, hero))

            matches.sort(reverse=True)
            best_score, best_hero = matches[0]
            second_score, second_hero = matches[1]
            margin = best_score - second_score

            confident = (
                best_score >= MIN_SCORE
                and margin >= MIN_MARGIN
            )
            result = best_hero if confident else "UNKNOWN"

            print(
                f"{team} {slot}: {result} | "
                f"best={best_hero} ({best_score:.3f}), "
                f"next={second_hero} ({second_score:.3f})"
            )