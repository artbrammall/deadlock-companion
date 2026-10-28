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


def detail_features(image):
    """Suppress smooth background visible through translucent portraits."""
    grey = cv2.cvtColor(cv2.resize(image, (74, 88)), cv2.COLOR_BGR2GRAY)
    grey = grey.astype(np.float32)
    return grey - cv2.GaussianBlur(grey, (0, 0), 1.5)


def rank_hero_matches(matches):
    """Compare distinct heroes, not two reference versions of the same hero."""
    best = {}
    for score, template_id, *extra in matches:
        hero = template_id.split("__", 1)[0]
        entry = (score, hero, *extra)
        if hero not in best or score > best[hero][0]:
            best[hero] = entry
    return sorted(best.values(), reverse=True)


class HeroRecognizer:
    def __init__(self, portraits_folder, min_score=0.75, min_margin=0.08):
        self.min_score = min_score
        self.min_margin = min_margin
        self.references = {}
        self.detail_references = {}
        self.full_detail_references = {}

        folder = Path(portraits_folder)
        paths = [(path.stem, path) for path in sorted(folder.glob("*.png"))]
        # Keep variants nested so roster tools do not mistake them for heroes.
        for path in sorted((folder / "variants").glob("*/*.png")):
            hero = path.parent.name
            if not (folder / f"{hero}.png").is_file():
                raise ValueError(f"Variant has no base hero portrait: {path}")
            paths.append((f"{hero}__{path.stem}", path))

        for template_id, path in paths:
            image = cv2.imread(str(path))
            if image is None:
                raise RuntimeError(f"Cannot read reference: {path}")

            self.references[template_id] = prepare(image)
            self.full_detail_references[template_id] = detail_features(image)
            self.detail_references[template_id] = self.full_detail_references[template_id][20:60, 20:54]

        if len({key.split("__", 1)[0] for key in self.references}) < 2:
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

        matches = rank_hero_matches(matches)
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

    def recognize_faded(self, image, first_enemy=False):
        """Conservative fallback, only used after normal recognition fails."""
        features = detail_features(image)
        search = features[17:63, 17:57]
        mask = np.ones((40, 34), dtype=np.uint8)
        if first_enemy:
            # Fixed 1760x990 HUD banner overlaps the left/lower face.
            # Include padding for search shifts and Gaussian filter support.
            yy, xx = np.mgrid[20:60, 20:54]
            mask[(xx < 49) & (yy >= 31)] = 0

        matches = []
        for hero, reference in self.detail_references.items():
            scores = cv2.matchTemplate(
                search, reference, cv2.TM_CCOEFF_NORMED, mask=mask
            )
            finite = scores[np.isfinite(scores)]
            score = float(finite.max()) if finite.size else -1.0
            matches.append((score, hero))

        matches = rank_hero_matches(matches)
        score, hero = matches[0]
        margin = score - matches[1][0]
        accepted = score >= self.min_score and margin >= max(self.min_margin, 0.12)
        return {
            "hero": hero if accepted else "UNKNOWN",
            "best_match": hero, "score": score, "margin": margin,
            "method": "background_suppressed_masked" if first_enemy else "background_suppressed",
        }

    def recognize_regions(self, image, first_enemy=False):
        """Require two disjoint detailed regions to agree at the same offset.

        A background edge may spoil one part of a translucent portrait while
        leaving other parts readable. Scores are not probabilities.
        """
        features = detail_features(image)
        regions = [
            (14, 10, 38, 34), (38, 10, 62, 34),
            (14, 34, 38, 58), (38, 34, 62, 58),
            (14, 58, 38, 82), (38, 58, 62, 82),
        ]
        if first_enemy:
            # Avoid the team banner, including search/filter padding.
            regions = [
                (14, 10, 38, 34), (38, 10, 62, 34),
                (45, 38, 69, 62), (45, 62, 69, 86),
            ]
        matches = []
        for hero, reference in self.full_detail_references.items():
            maps = []
            for x, y, right, bottom in regions:
                scores = cv2.matchTemplate(
                    features[y - 2:bottom + 2, x - 2:right + 2],
                    reference[y:bottom, x:right], cv2.TM_CCOEFF_NORMED,
                )
                scores = np.where(np.isfinite(scores), scores, -1.0)
                maps.append(scores)
            ordered = np.sort(np.stack(maps), axis=0)
            # Both regions must contribute strong evidence; one good fragment
            # cannot compensate for an unrelated second fragment.
            supported = ordered[-2] >= 0.75
            combined = (ordered[-1] + ordered[-2]) / 2
            best = np.unravel_index(combined.argmax(), combined.shape)
            score = float(combined[best])
            matches.append((score, hero, bool(supported[best])))
        matches = rank_hero_matches(matches)
        score, hero, supported = matches[0]
        margin = score - matches[1][0]
        accepted = supported and score >= max(self.min_score, 0.85) and margin >= max(self.min_margin, 0.20)
        return {
            "hero": hero if accepted else "UNKNOWN",
            "best_match": hero, "score": score, "margin": margin,
            "method": "two_region_agreement",
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

            for slot, (left, top, right, bottom) in enumerate(layout[f"{team}_portraits"]):
                if not (
                    0 <= left < right <= width
                    and 0 <= top < bottom <= height
                ):
                    raise ValueError(f"Invalid {team} portrait rectangle")

                crop = screenshot[top:bottom, left:right]
                result = self.recognize(crop)
                if team == "enemy" and result["hero"] == "UNKNOWN":
                    result = self.recognize_faded(crop, first_enemy=(slot == 0))
                    if result["hero"] == "UNKNOWN":
                        regional = self.recognize_regions(crop, first_enemy=(slot == 0))
                        if regional["hero"] != "UNKNOWN":
                            result = regional
                teams[team].append(result)

        return teams