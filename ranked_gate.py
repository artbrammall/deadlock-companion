"""Conservative visual gate for the supplied competitive UI.

BANNED HEROES is evidence, not an authoritative game-mode API. Only enable
during pregame after seeing that marker. Expire across gameplay/loading and
after 90 seconds, so an old confirmation cannot silently enable another match.
"""
import time
from pathlib import Path

import numpy as np

from screen_state import text_features, similarity


BANNED_HEADER = (47, 210, 195, 224)


class RankedPregameGate:
    def __init__(self, template_folder, resolution=(1760, 990)):
        self.resolution = tuple(resolution)
        self.reference = np.load(
            Path(template_folder) / "ranked_banned_header.npy", allow_pickle=False
        )
        self.expires_at = None

    def marker_score(self, frame):
        height, width = frame.shape[:2]
        if (width, height) != self.resolution:
            return 0.0
        left, top, right, bottom = BANNED_HEADER
        return max(
            similarity(self.reference, text_features(
                frame, (left + dx, top + dy, right + dx, bottom + dy)
            ))
            for dy in range(-3, 4) for dx in range(-3, 4)
        )

    def update(self, frame, state, now=None):
        now = time.monotonic() if now is None else now
        if self.expires_at is not None and now >= self.expires_at:
            self.expires_at = None
        if state != "PREGAME":
            if state not in {"PAUSE_MENU", "HERO_SELECTION", "WRONG_RESOLUTION"}:
                self.expires_at = None
            return False
        if self.marker_score(frame) >= 0.85:
            self.expires_at = now + 90.0
        return self.expires_at is not None
