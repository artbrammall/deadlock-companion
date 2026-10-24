import json
import time
from pathlib import Path

import dxcam
import cv2

import sys
import threading

from recognition import HeroRecognizer
from screen_state import ScreenStateDetector
from self_detection import detect_self
from roster import get_roster
from recommendations import eligible_heroes
from stats_cache import load_scorer
from opportunity import OpportunityScorer


GUI_MODE = "--gui" in sys.argv
stop_requested = threading.Event()


def emit_event(event):
    if GUI_MODE:
        print("@@EVENT " + json.dumps(event), flush=True)


def listen_for_stop():
    for line in sys.stdin:
        if line.strip() == "stop":
            break
    stop_requested.set()


if GUI_MODE:
    threading.Thread(target=listen_for_stop, daemon=True).start()


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

scorer = load_scorer()
if scorer is not None:
    print(f"Statistics downloaded: {scorer.downloaded_at}")

opportunity_scorer = None

if scorer is not None:
    try:
        opportunity_scorer = OpportunityScorer(scorer)
    except (ValueError, KeyError) as error:
        print(f"Best Opportunity unavailable: {error}", flush=True)

state_detector = ScreenStateDetector(
    ROOT / "screen_templates",
    resolution=layout["resolution"],
)

candidate = None
matching_scans = 0
confirmed = None
last_message = None

STALE_AFTER_SECONDS = 1.5
last_frame_at = None


def report(message):
    global last_message
    if message != last_message:
        print(message, flush=True)
        last_message = message
        emit_event({"type": "status", "message": message})


def reset(message):
    global candidate, matching_scans, confirmed
    candidate = None
    matching_scans = 0
    confirmed = None
    report(message)


last_debug_save = {}


def save_failure(reason, frame, details):
    now = time.monotonic()

    if now - last_debug_save.get(reason, -float("inf")) < 3:
        return

    last_debug_save[reason] = now
    base = DEBUG / f"{reason}_{time.time_ns()}"

    if cv2.imwrite(str(base.with_suffix(".png")), frame):
        base.with_suffix(".json").write_text(
            json.dumps(details, indent=2),
            encoding="utf-8",
        )
        print(f"DEBUG: saved {base.name}", flush=True)


print("Live detection starting. Switch to Deadlock.")
print("Stop with Ctrl+C in this terminal.")

camera = dxcam.create(
    device_idx=DEVICE,
    output_idx=MONITOR,
    output_color="BGR",
)

try:
    while not stop_requested.is_set():
        started = time.monotonic()

        try:
            frame = camera.grab()

            if frame is None:
                # Missing frames break consecutive-scan agreement.
                candidate = None
                matching_scans = 0

                if (
                    last_frame_at is None
                    or time.monotonic() - last_frame_at
                    >= STALE_AFTER_SECONDS
                ):
                    reset("PAUSED: capture stale; current lineup cleared.")

                continue

            last_frame_at = time.monotonic()

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
                save_failure(
                    "incomplete_lineup",
                    frame,
                    results,
                )
                reset("WAITING: no complete, unique 6v6 lineup detected.")
                continue

            self_slot = detect_self(frame, layout)
            observation = (snapshot, self_slot)

            if observation == candidate:
                matching_scans += 1
            else:
                candidate = observation
                matching_scans = 1
                if observation != confirmed:
                    confirmed = None
                report("CHECKING: awaiting consecutive matching scans.")

            if matching_scans >= required_scans and observation != confirmed:
                confirmed = observation

                allies, enemies = snapshot

                current_hero = (
                    None if self_slot is None else allies[self_slot]
                )

                you = (
                    "UNKNOWN"
                    if current_hero is None
                    else f"{current_hero} (ally slot {self_slot + 1})"
                )

                choices = eligible_heroes(
                    get_roster(), allies, enemies, current_hero
                )

                ranking_lines = []
                ranked = []

                if scorer is None:
                    ranking_lines.append(
                        "Recommendations unavailable: no usable statistics."
                    )
                elif choices:
                    # Remove your current hero before evaluating replacements.
                    teammates = [
                        hero for hero in allies
                        if hero != current_hero
                    ]

                    try:
                        ranked = [
                            scorer.score(hero, teammates, enemies)
                            for hero in choices
                        ]
                        if opportunity_scorer is not None:
                            for result in ranked:
                                result.update(
                                    opportunity_scorer.describe(result)
                                )
                        ranked.sort(
                            key=lambda result: (
                                -result["score"], result["hero"]
                            )
                        )

                        for position, result in enumerate(ranked, start=1):
                            hero = result["hero"]
                            label = (
                                f"{hero} (stay)"
                                if hero == current_hero
                                else hero
                            )

                            ranking_lines.append(
                                f"{position}. {label}: "
                                f"{result['score']:.2f} points "
                                f"[base {result['baseline_pct']:.2f}, "
                                f"enemies {result['matchup_points']:+.2f}, "
                                f"allies {result['synergy_points']:+.2f}]"
                            )

                            if result["missing"]:
                                ranking_lines.append(
                                    "   Missing pair data: "
                                    + ", ".join(result["missing"])
                                )

                    except ValueError as error:
                        ranked = []
                        ranking_lines = [
                            f"Recommendations unavailable: {error}"
                        ]
                else:
                    ranking_lines.append(
                        "Unavailable: identity or lineup uncertain"
                    )

                ranking_text = "\n".join(ranking_lines)

                report(
                    f"\nCONFIRMED\n"
                    f"You:     {you}\n"
                    f"Allies:  {', '.join(allies)}\n"
                    f"Enemies: {', '.join(enemies)}\n"
                    f"Suggested picks from visible lineup:\n"
                    f"{ranking_text}\n"
                    "Scores are ranking points, not win probabilities.\n"
                    "Enemy picks may have changed. Confirm availability in-game."
                )

                emit_event({
                    "type": "lineup",
                    "current_hero": current_hero,
                    "self_slot": self_slot,
                    "allies": list(allies),
                    "enemies": list(enemies),
                    "ranked": ranked,
                    "downloaded_at": (
                        scorer.downloaded_at if scorer is not None else None
                    ),
                    "unavailable": (
                        None if ranked else "\n".join(ranking_lines)
                    ),
                })

        finally:
            emit_event({"type": "heartbeat"})
            elapsed = time.monotonic() - started
            stop_requested.wait(max(0, interval - elapsed))

except KeyboardInterrupt:
    print("\nStopped.")

finally:
    camera.release()