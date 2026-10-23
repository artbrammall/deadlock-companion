import time
from pathlib import Path

import cv2
import dxcam
import shutil

DEVICE = 0
MONITOR = 0

print("Available monitors:")
print(dxcam.output_info())

folder = Path(__file__).parent / "captures"

if folder.exists():
    shutil.rmtree(folder)

folder.mkdir()

print("Switch to Deadlock now. Capture begins in 10 seconds.")
time.sleep(10)

camera = dxcam.create(
    device_idx=DEVICE,
    output_idx=MONITOR,
    output_color="BGR",
)

try:
    for number in range(30):
        frame = camera.grab()

        if frame is None:
            print("No new frame available.")
        else:
            path = folder / f"{number:03d}.png"
            if not cv2.imwrite(str(path), frame):
                raise RuntimeError(f"Could not save {path}")

            height, width = frame.shape[:2]
            print(f"Saved {path.name}: {width} x {height}")

        time.sleep(2)
finally:
    camera.release()

print(f"Finished. Screenshots: {folder}")