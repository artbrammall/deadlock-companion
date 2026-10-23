from pathlib import Path

import cv2
import numpy as np

from screen_state import MARKERS, text_features

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "screen_templates"
OUTPUT.mkdir(exist_ok=True)

for state, (filename, rectangle) in MARKERS.items():
    source = ROOT / "tests" / "samples" / filename
    image = cv2.imread(str(source))

    if image is None:
        raise RuntimeError(f"Cannot read: {source}")

    if image.shape[:2] != (990, 1760):
        raise ValueError(f"Wrong resolution: {source}")

    features = text_features(image, rectangle)
    destination = OUTPUT / f"{state.lower()}.npy"
    np.save(destination, features)
    print(f"Saved {destination.name}")