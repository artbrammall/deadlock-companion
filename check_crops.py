import json
from pathlib import Path

import cv2

ROOT = Path(__file__).parent

with (ROOT / "screen_config.json").open() as file:
    config = json.load(file)

layout = config["layouts"][config["active_layout"]]
expected_width, expected_height = layout["resolution"]

for source in sorted((ROOT / "samples").glob("*.png")):
    filename = source.name
    screenshot = cv2.imread(str(source))

    if screenshot is None:
        raise RuntimeError(f"Cannot read image: {source}")

    height, width = screenshot.shape[:2]
    if (width, height) != (expected_width, expected_height):
        raise RuntimeError(
            f"{filename}: expected {expected_width}x{expected_height}, "
            f"got {width}x{height}"
        )

    output = ROOT / "debug_crops" / source.stem
    output.mkdir(parents=True, exist_ok=True)

    regions = {}

    for team in ["ally", "enemy"]:
        for slot, rectangle in enumerate(
            layout[f"{team}_portraits"], start=1
        ):
            regions[f"{team}_{slot}"] = rectangle

    regions["pregame_text"] = layout["pregame_text"]
    regions["scoreboard_panel"] = layout["scoreboard_panel"]

    for name, (left, top, right, bottom) in regions.items():
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError(f"Invalid rectangle: {name}")

        crop = screenshot[top:bottom, left:right]
        destination = output / f"{name}.png"

        if not cv2.imwrite(str(destination), crop):
            raise RuntimeError(f"Cannot save: {destination}")

    print(f"{filename}: saved crops to {output}")

print("Done.")