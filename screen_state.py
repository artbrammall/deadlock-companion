from pathlib import Path

import numpy as np


# State: (reference screenshot, text rectangle)
MARKERS = {
    "PAUSE_MENU": ("pause_menu.png", (110, 252, 383, 285)),
    "HERO_SELECTION": ("hero_selection.png", (245, 60, 345, 98)),
    "LOADING": ("pregame_character.png", (85, 33, 350, 57)),
    "PREGAME": ("009.png", (752, 552, 1008, 575)),
}


def text_features(image, rectangle):
    left, top, right, bottom = rectangle

    # Include a one-pixel border to calculate text edges.
    crop = image[top - 1:bottom, left - 1:right]
    grey = crop.astype(np.float32).mean(axis=2)

    horizontal = np.diff(grey, axis=1, prepend=grey[:, :1])
    vertical = np.diff(grey, axis=0, prepend=grey[:1, :])

    return np.hypot(horizontal, vertical)[1:, 1:]


def similarity(first, second):
    first = first - first.mean()
    second = second - second.mean()

    denominator = np.sqrt(
        np.sum(first * first) * np.sum(second * second)
    )

    if denominator < 1e-8:
        return 0.0

    return float(np.sum(first * second) / denominator)


class ScreenStateDetector:
    def __init__(self, template_folder, resolution=(1760, 990)):
        self.resolution = tuple(resolution)
        self.threshold = 0.80
        self.templates = {}

        for state in MARKERS:
            path = Path(template_folder) / f"{state.lower()}.npy"
            self.templates[state] = np.load(path, allow_pickle=False)

    def detect(self, frame):
        height, width = frame.shape[:2]

        if (width, height) != self.resolution:
            return "WRONG_RESOLUTION", {}

        scores = {}

        for state, (_, rectangle) in MARKERS.items():
            left, top, right, bottom = rectangle
            best = -1.0

            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    shifted = (
                        left + dx, top + dy,
                        right + dx, bottom + dy,
                    )
                    features = text_features(frame, shifted)
                    score = similarity(self.templates[state], features)
                    best = max(best, score)

            scores[state] = best

        # Explicit priority: menus/loading block pregame detection.
        for state in MARKERS:
            if scores[state] >= self.threshold:
                return state, scores

        return "NOT_PREGAME", scores