"""Conservative visual gate for the supplied competitive UI.

BANNED HEROES is evidence, not an authoritative game-mode API. Only enable
during pregame after seeing that marker. Brief unidentified transitions retain
mode evidence, but never permit recommendations on an unidentified frame.
"""
import time
from pathlib import Path

import numpy as np

from screen_state import text_features, similarity


BANNED_HEADER = (47, 210, 195, 224)
TRANSITION_GRACE_SECONDS = 5.0


class RankedPregameGate:
    def __init__(self, template_folder, resolution=(1760, 990)):
        self.resolution = tuple(resolution)
        self.reference = np.load(
            Path(template_folder) / "ranked_banned_header.npy", allow_pickle=False
        )
        self.expires_at = None
        self.non_pregame_since = None

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
        # Check before processing a returning PREGAME frame: a long transition
        # must not revive old mode evidence after a capture gap.
        if (self.non_pregame_since is not None
                and now - self.non_pregame_since >= TRANSITION_GRACE_SECONDS):
            self.expires_at = None

        if state == "LOADING":
            self.expires_at = None
            self.non_pregame_since = None
            return False
        if state != "PREGAME":
            if state not in {"PAUSE_MENU", "HERO_SELECTION", "WRONG_RESOLUTION"}:
                if self.non_pregame_since is None:
                    self.non_pregame_since = now
            return False

        self.non_pregame_since = None
        if self.marker_score(frame) >= 0.85:
            self.expires_at = now + 90.0
        return self.expires_at is not None
