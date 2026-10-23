from pathlib import Path

import cv2
import numpy as np


def prepare(image, search=False):
    image = cv2.resize(image, (74, 88))

    if search:
        # Central portrait area, with three pixels of search padding.
        image = image[17:63, 17:57]
    else:
        # Focus on the centre, avoiding peripheral UI/background.
        image = image[20:60, 20:54]

    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


class HeroRecognizer:
    def __init__(self, portraits_folder, min_score=0.75, min_margin=0.08):
        self.min_score = min_score
        self.min_margin = min_margin
        self.references = {}

        for path in sorted(Path(portraits_folder).glob("*.png")):
            image = cv2.imread(str(path))
            if image is None:
                raise RuntimeError(f"Cannot read reference: {path}")

            self.references[path.stem] = prepare(image)

        if len(self.references) < 2:
            raise RuntimeError("At least two reference portraits are required.")

    def recognize(self, image):
        portrait = prepare(image, search=True)
        matches = []

        for hero, reference in self.references.items():
            score = float(cv2.matchTemplate(
                portrait, reference, cv2.TM_CCOEFF_NORMED
            ).max())

            if not np.isfinite(score):
                score = -1.0

            matches.append((score, hero))

        matches.sort(reverse=True)
        score, best_hero = matches[0]
        margin = score - matches[1][0]

        accepted = (
            score >= self.min_score
            and margin >= self.min_margin
        )

        return {
            "hero": best_hero if accepted else "UNKNOWN",
            "best_match": best_hero,
            "score": score,
            "margin": margin,
        }

    def recognize_teams(self, screenshot, layout):
        height, width = screenshot.shape[:2]

        if [width, height] != layout["resolution"]:
            raise ValueError(
                f"Expected {layout['resolution']}, got {[width, height]}"
            )

        teams = {}

        for team in ["ally", "enemy"]:
            teams[team] = []

            for left, top, right, bottom in layout[f"{team}_portraits"]:
                if not (
                    0 <= left < right <= width
                    and 0 <= top < bottom <= height
                ):
                    raise ValueError(f"Invalid {team} portrait rectangle")

                crop = screenshot[top:bottom, left:right]
                teams[team].append(self.recognize(crop))

        return teams