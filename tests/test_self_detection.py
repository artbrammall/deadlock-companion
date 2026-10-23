import json
from pathlib import Path

import cv2
import numpy as np

from self_detection import detect_self

ROOT = Path(__file__).resolve().parent.parent

with (ROOT / "screen_config.json").open() as file:
    config = json.load(file)

layout = config["layouts"][config["active_layout"]]

# Expected slot numbers here are human-readable: 1–6.
cases = {
    "009.png": 5,
    "010.png": 1,
    "012.png": 1,
    "001.png": 6,
    "match2_normal.png": 1,
    "match2_tab.png": 3,
}

passed = 0
failed = 0

for filename, expected in cases.items():
    image = cv2.imread(str(ROOT / "tests" / "samples" / filename))

    if image is None:
        raise RuntimeError(f"Cannot read: {filename}")

    slot = detect_self(image, layout)
    actual = None if slot is None else slot + 1

    correct = actual == expected
    passed += int(correct)
    failed += int(not correct)

    print(
        f"{'PASS' if correct else 'FAIL'} {filename}: "
        f"expected slot {expected}, got {actual}"
    )

blank = np.zeros((990, 1760, 3), dtype=np.uint8)
correct = detect_self(blank, layout) is None
passed += int(correct)
failed += int(not correct)
print(f"{'PASS' if correct else 'FAIL'} blank screen")

print(f"\nResults: {passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)