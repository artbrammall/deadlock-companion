import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "real_lineups.json"

SEED = 84217
BLOCK_SECONDS = 6 * 60 * 60
WINDOW_SECONDS = 20 * 60
PAGE_SIZE = 500
REQUEST_INTERVAL = 2.2


def main():
    stats = json.loads(
        (ROOT / "data" / "hero_stats.json").read_text(encoding="utf-8")
    )
    mapping = json.loads(
        (ROOT / "hero_ids.json").read_text(encoding="utf-8")
    )
    known_ids = set(mapping.values())

    start = stats["filters"]["min_unix_timestamp"]
    end = stats["filters"]["max_unix_timestamp"]

    if end <= start:
        raise ValueError("Invalid statistics time window.")

    # Select time windows independently of match contents.
    rng = random.Random(SEED)
    windows = []

    for block_start in range(start, end, BLOCK_SECONDS):
        block_end = min(block_start + BLOCK_SECONDS, end)
        possible_starts = list(
            range(block_start, block_end, WINDOW_SECONDS)
        )
        window_start = rng.choice(possible_starts)
        window_end = min(window_start + WINDOW_SECONDS, block_end)
        windows.append((window_start, window_end))

    records = {}
    skipped = Counter()
    downloaded_count = 0
    last_request_at = 0.0

    with httpx.Client(
        base_url="https://api.deadlock-api.com",
        timeout=120,
        follow_redirects=True,
    ) as client:
        for index, (window_start, window_end) in enumerate(windows, 1):
            print(
                f"Window {index}/{len(windows)}: "
                f"{datetime.fromtimestamp(window_start, timezone.utc).isoformat()}",
                flush=True,
            )

            cursor = None

            while True:
                params = {
                    **stats["filters"],
                    "min_unix_timestamp": window_start,
                    "max_unix_timestamp": window_end - 1,
                    "include_info": "true",
                    "include_player_info": "true",
                    "order_by": "match_id",
                    "order_direction": "desc",
                    "limit": PAGE_SIZE,
                }

                if cursor is not None:
                    params["max_match_id"] = cursor

                # Stay below the documented 30 requests/minute limit.
                elapsed = time.monotonic() - last_request_at
                time.sleep(max(0, REQUEST_INTERVAL - elapsed))
                last_request_at = time.monotonic()

                response = client.get(
                    "/v1/matches/metadata",
                    params=params,
                )
                response.raise_for_status()
                matches = response.json()

                if not isinstance(matches, list):
                    raise ValueError("Expected a list of matches.")
                if not matches:
                    break

                downloaded_count += len(matches)

                for match in matches:
                    players = match.get("players") or []

                    if len(players) != 12:
                        skipped["not_12_players"] += 1
                        continue

                    teams = {"Team0": [], "Team1": []}
                    invalid = False

                    for player in players:
                        team = player.get("team")
                        hero_id = player.get("hero_id")

                        if team not in teams or hero_id not in known_ids:
                            invalid = True
                            break

                        teams[team].append(hero_id)

                    if invalid:
                        skipped["unknown_team_or_hero"] += 1
                        continue

                    if any(len(team) != 6 for team in teams.values()):
                        skipped["not_6v6"] += 1
                        continue

                    all_ids = teams["Team0"] + teams["Team1"]
                    if len(set(all_ids)) != 12:
                        skipped["duplicate_heroes"] += 1
                        continue

                    match_id = match["match_id"]
                    if match_id in records:
                        skipped["duplicate_match"] += 1
                        continue

                    records[match_id] = {
                        "match_id": match_id,
                        "start_time": match["start_time"],
                        "team0": sorted(teams["Team0"]),
                        "team1": sorted(teams["Team1"]),
                        # Preserve null when unavailable, rather than
                        # claiming that no heroes were banned.
                        "banned_hero_ids": match.get("banned_hero_ids"),
                        "average_badge": match.get("average_badge"),
                    }

                if len(matches) < PAGE_SIZE:
                    break

                next_cursor = min(
                    match["match_id"] for match in matches
                ) - 1

                if cursor is not None and next_cursor >= cursor:
                    raise ValueError("Pagination failed to advance.")

                cursor = next_cursor

            print(f"  Valid unique lineups so far: {len(records):,}")

    if not records:
        raise ValueError("No valid lineups were collected.")

    lineups = sorted(
        records.values(),
        key=lambda row: (row["start_time"], row["match_id"]),
    )

    output = {
        "schema_version": 1,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "stats_downloaded_at": stats["downloaded_at"],
        "filters": stats["filters"],
        "sampling": {
            "seed": SEED,
            "block_seconds": BLOCK_SECONDS,
            "window_seconds": WINDOW_SECONDS,
            "windows": windows,
            "hero_field": "hero_id",
        },
        "skipped": dict(skipped),
        "lineups": lineups,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)

    appearances = Counter()
    for lineup in lineups:
        appearances.update(lineup["team0"] + lineup["team1"])

    print(f"\nDownloaded records: {downloaded_count:,}")
    print(f"Valid unique matches: {len(lineups):,}")
    print(f"Skipped: {dict(skipped)}")
    print("\nHero appearances in sampled matches:")

    for name, hero_id in sorted(mapping.items()):
        count = appearances[hero_id]
        print(
            f"{name:18} {count:6,d} matches "
            f"({100 * count / len(lineups):5.1f}%)"
        )

    print(f"\nSaved {OUTPUT}")


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"\nDownload failed: {error}")
        print("Any existing real_lineups.json has been kept.")
        raise SystemExit(1)