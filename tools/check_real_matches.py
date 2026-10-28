import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_paths import DATA_DIR
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    stats = json.loads(
        (DATA_DIR / "hero_stats.json").read_text(encoding="utf-8")
    )

    # Use the same mode and time window as our statistics.
    params = {
        **stats["filters"],
        "include_info": "true",
        "include_player_info": "true",
        "order_by": "match_id",
        "order_direction": "desc",
        "limit": 20,
    }

    print("Downloading 20 recorded matches...", flush=True)

    response = httpx.get(
        "https://api.deadlock-api.com/v1/matches/metadata",
        params=params,
        timeout=120,
        follow_redirects=True,
    )
    response.raise_for_status()
    matches = response.json()

    if not isinstance(matches, list) or not matches:
        raise ValueError("Expected a non-empty list of matches.")

    output = DATA_DIR / "real_matches_sample.json"
    output.write_text(
        json.dumps(
            {"query": params, "matches": matches},
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Received {len(matches)} matches.")
    print(f"Saved {output}")

    first = matches[0]
    print("\nMatch fields:", ", ".join(first.keys()))

    players = first.get("players")
    if not isinstance(players, list) or not players:
        print("No player list found. Inspect the saved response.")
        return

    print("Player fields:", ", ".join(players[0].keys()))
    print("\nFirst match's hero/team fields:")

    for player in players:
        # Print lineup information rather than player account details.
        fields = {
            key: value
            for key, value in player.items()
            if "hero" in key or "team" in key
        }
        print(json.dumps(fields))

    total_players = 0
    known_pregame = 0
    complete_pregame_matches = 0

    for match in matches:
        match_players = match.get("players") or []
        known = sum(
            player.get("pregame_hero_id") is not None
            for player in match_players
        )

        total_players += len(match_players)
        known_pregame += known

        if len(match_players) == 12 and known == 12:
            complete_pregame_matches += 1

    print(
        f"\nPregame hero IDs available: "
        f"{known_pregame}/{total_players} player records"
    )
    print(
        "Matches with all 12 pregame hero IDs: "
        f"{complete_pregame_matches}/{len(matches)}"
    )


if __name__ == "__main__":
    main()