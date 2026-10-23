from pathlib import Path

import cv2
import numpy as np

from screen_state import ScreenStateDetector

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "tests" / "samples"

detector = ScreenStateDetector(ROOT / "screen_templates")

cases = {
    "010.png": "PREGAME",
    "012.png": "PREGAME",
    "match2_normal.png": "PREGAME",
    "match2_tab.png": "PREGAME",
    "001.png": "NOT_PREGAME",
    "002.png": "NOT_PREGAME",
    "003.png": "NOT_PREGAME",
    "005.png": "NOT_PREGAME",
    "not_pregame.png": "NOT_PREGAME",
    "pause_menu.png": "PAUSE_MENU",
    "hero_selection.png": "HERO_SELECTION",
    "pregame_character.png": "LOADING",
}

passed = 0
failed = 0


def check(label, frame, expected):
    global passed, failed

    actual, scores = detector.detect(frame)
    correct = actual == expected

    if correct:
        passed += 1
    else:
        failed += 1

    print(
        f"{'PASS' if correct else 'FAIL'} {label}: "
        f"expected={expected}, got={actual}"
    )

    if not correct:
        print("Scores:", scores)


for filename, expected in cases.items():
    image = cv2.imread(str(SAMPLES / filename))

    if image is None:
        raise RuntimeError(f"Cannot read sample: {filename}")

    check(filename, image, expected)

check(
    "black frame",
    np.zeros((990, 1760, 3), dtype=np.uint8),
    "NOT_PREGAME",
)

check(
    "1080p frame",
    np.zeros((1080, 1920, 3), dtype=np.uint8),
    "WRONG_RESOLUTION",
)

print(f"\nResults: {passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)