import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "hero_stats.json"

# Use the same seven-day window for every dataset.
end_time = int(time.time())
filters = {
    "game_mode": "normal",
    "match_mode": "ranked",
    "min_unix_timestamp": end_time - 7 * 24 * 60 * 60,
    "max_unix_timestamp": end_time,
}

requests = {
    "overall": (
        "hero-stats",
        {"bucket": "no_bucket"},
    ),
    "matchups": (
        "hero-counter-stats",
        {"same_lane_filter": "false", "min_matches": 1},
    ),
    "synergies": (
        "hero-synergy-stats",
        {"same_lane_filter": "false", "min_matches": 1},
    ),
}


def main():
    datasets = {}

    with httpx.Client(
        base_url="https://api.deadlock-api.com",
        timeout=120,
        follow_redirects=True,
    ) as client:
        for name, (endpoint, extra_filters) in requests.items():
            print(f"Downloading {name}...", flush=True)

            response = client.get(
                f"/v1/analytics/{endpoint}",
                params={**filters, **extra_filters},
            )
            response.raise_for_status()
            rows = response.json()

            if not isinstance(rows, list) or not rows:
                raise ValueError(f"{name}: expected a non-empty list.")

            if not all(isinstance(row, dict) for row in rows):
                raise ValueError(f"{name}: unexpected row format.")

            datasets[name] = rows
            print(f"  {len(rows)} rows")
            print(f"  Example: {json.dumps(rows[0])}")

    cache = {
        "schema_version": 1,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "endpoint_filters": {
            name: extra for name, (_, extra) in requests.items()
        },
        "datasets": datasets,
    }

    # Replace the previous cache only after every download succeeds.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(cache, indent=2),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(f"\nSaved {OUTPUT}")


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, ValueError, OSError) as error:
        print(f"\nUpdate failed: {error}")
        print("Any existing cache has been kept.")
        raise SystemExit(1)