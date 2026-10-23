import json
import time
from pathlib import Path

import dxcam
import cv2

from recognition import HeroRecognizer
from screen_state import ScreenStateDetector

ROOT = Path(__file__).resolve().parent
DEBUG = ROOT / "debug_live"
DEBUG.mkdir(exist_ok=True)

DEVICE = 0
MONITOR = 0

with (ROOT / "screen_config.json").open() as file:
    config = json.load(file)

layout = config["layouts"][config["active_layout"]]
interval = float(config["scan_interval_seconds"])
required_scans = int(config["confirmation_scans"])

if interval <= 0 or required_scans < 2:
    raise ValueError("Use a positive interval and at least two scans.")

recognizer = HeroRecognizer(ROOT / "portraits")

state_detector = ScreenStateDetector(
    ROOT / "screen_templates",
    resolution=layout["resolution"],
)

candidate = None
matching_scans = 0
confirmed = None
last_message = None


def report(message):
    global last_message
    if message != last_message:
        print(message, flush=True)
        last_message = message


def reset(message):
    global candidate, matching_scans, confirmed
    candidate = None
    matching_scans = 0
    confirmed = None
    report(message)


print("Live detection starting. Switch to Deadlock.")
print("Stop with Ctrl+C in this terminal.")

camera = dxcam.create(
    device_idx=DEVICE,
    output_idx=MONITOR,
    output_color="BGR",
)

try:
    while True:
        started = time.monotonic()

        try:
            frame = camera.grab()

            if frame is None:
                reset("PAUSED: waiting for a fresh frame at game resolution.")
                continue

            height, width = frame.shape[:2]
            if [width, height] != layout["resolution"]:
                reset("PAUSED: waiting for a fresh frame at game resolution.")
                continue

            state, _ = state_detector.detect(frame)

            if state != "PREGAME":
                reset(f"WAITING: {state}; current lineup cleared.")
                continue

            results = recognizer.recognize_teams(frame, layout)

            snapshot = tuple(
                tuple(result["hero"] for result in results[team])
                for team in ["ally", "enemy"]
            )

            all_unknown = all(
                hero == "UNKNOWN"
                for team in snapshot
                for hero in team
            )

            if (
                all_unknown
                and last_message
                != "WAITING: no recognised portraits; current lineup cleared."
            ):
                path = DEBUG / "last_unknown.png"
                if cv2.imwrite(str(path), frame):
                    print(
                        f"DEBUG: saved unrecognised frame to {path}",
                        flush=True,
                    )

            if all_unknown:
                reset("WAITING: no recognised portraits; current lineup cleared.")
                continue

            heroes = [
                hero
                for team in snapshot
                for hero in team
            ]

            if (
                len(heroes) != 12
                or "UNKNOWN" in heroes
                or len(set(heroes)) != 12
            ):
                reset("WAITING: no complete, unique 6v6 lineup detected.")
                continue

            if snapshot == candidate:
                matching_scans += 1
            else:
                candidate = snapshot
                matching_scans = 1
                confirmed = None
                report("CHECKING: lineup changed; awaiting confirmation.")

            if matching_scans >= required_scans and snapshot != confirmed:
                confirmed = snapshot

                allies, enemies = snapshot
                report(
                    f"\nCONFIRMED\n"
                    f"Allies:  {', '.join(allies)}\n"
                    f"Enemies: {', '.join(enemies)}"
                )

        finally:
            elapsed = time.monotonic() - started
            time.sleep(max(0, interval - elapsed))

except KeyboardInterrupt:
    print("\nStopped.")

finally:
    camera.release()