import json
from pathlib import Path

import cv2

from recognition import HeroRecognizer

ROOT = Path(__file__).parent

with (ROOT / "screen_config.json").open() as file:
    config = json.load(file)

with (ROOT / "test_cases.json").open() as file:
    cases = json.load(file)

if not cases:
    raise RuntimeError("No test cases configured.")

layout = config["layouts"][config["active_layout"]]
recognizer = HeroRecognizer(ROOT / "portraits")

passed = 0
failed = 0

for filename, expected_teams in cases.items():
    screenshot = cv2.imread(str(ROOT / "samples" / filename))
    if screenshot is None:
        raise RuntimeError(f"Cannot read sample: {filename}")

    results = recognizer.recognize_teams(screenshot, layout)
    print(f"\n--- {filename} ---")

    for team in ["ally", "enemy"]:
        expected = expected_teams[team]
        detected = results[team]

        if len(expected) != len(detected):
            raise ValueError(f"{filename}: wrong number of {team} labels")

        for slot, (wanted, result) in enumerate(
            zip(expected, detected), start=1
        ):
            actual = result["hero"]
            correct = actual == wanted

            if correct:
                passed += 1
            else:
                failed += 1

            status = "PASS" if correct else "FAIL"
            print(
                f"{status} {team} {slot}: "
                f"expected={wanted}, got={actual} "
                f"(best={result['best_match']}, "
                f"score={result['score']:.3f})"
            )

print(f"\nResults: {passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)