import json
import re
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "hero_ids.json"


def normalize(name):
    # Example: "Mo & Krill" becomes "mo_and_krill".
    name = name.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


def main():
    # Read the hero IDs present in our downloaded statistics.
    cache = json.loads(
        (ROOT / "data" / "hero_stats.json").read_text(encoding="utf-8")
    )
    needed_ids = {
        row["hero_id"]
        for row in cache["datasets"]["overall"]
    }

    # Read the hero names recognised by our app.
    portrait_names = {
        path.stem for path in (ROOT / "portraits").glob("*.png")
    }
    if not portrait_names:
        raise ValueError("No PNG files found in portraits.")

    print("Downloading hero names...", flush=True)
    response = httpx.get(
        "https://api.deadlock-api.com/v1/assets/heroes",
        timeout=60,
        follow_redirects=True,
    )
    response.raise_for_status()
    heroes = response.json()

    if not isinstance(heroes, list):
        raise ValueError("Expected a list of hero objects.")

    mapping = {}
    seen_ids = set()
    problems = []

    for hero in heroes:
        hero_id = hero["id"]

        # Ignore heroes absent from the downloaded statistics.
        if hero_id not in needed_ids:
            continue

        if hero_id in seen_ids:
            problems.append(f"Duplicate API hero ID: {hero_id}")
            continue
        seen_ids.add(hero_id)

        name = normalize(hero["name"])

        if name not in portrait_names:
            problems.append(
                f"No portrait for {hero['name']!r} "
                f"(ID {hero_id}; expected {name}.png)"
            )
        elif name in mapping:
            problems.append(f"Multiple IDs match {name}")
        else:
            mapping[name] = hero_id

    for hero_id in sorted(needed_ids - seen_ids):
        problems.append(f"No API name found for ID {hero_id}")

    if problems:
        raise ValueError("\n".join(problems))

    # Only replace the mapping after every required hero matches.
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(mapping, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)

    for name, hero_id in sorted(mapping.items()):
        print(f"{name}: {hero_id}")

    unused = portrait_names - mapping.keys()
    if unused:
        print(f"\nPortraits without overall stats: {', '.join(sorted(unused))}")

    print(f"\nMapped {len(mapping)} heroes. Saved {OUTPUT}")


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, ValueError, OSError, KeyError, TypeError) as error:
        print(f"\nMapping failed: {error}")
        print("Any existing hero_ids.json has been kept.")
        raise SystemExit(1)