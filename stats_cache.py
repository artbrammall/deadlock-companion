import json
from datetime import datetime, timezone

import httpx

from scoring import PickScorer
from tools.update_stats import OUTPUT, main as update_stats, validate_cache

MAX_AGE_SECONDS = 60 * 60

CACHE_ERRORS = (OSError, ValueError, KeyError, TypeError)


def read_cache_age():
    cache = json.loads(OUTPUT.read_text(encoding="utf-8"))
    validate_cache(cache)

    downloaded = datetime.fromisoformat(cache["downloaded_at"])
    if downloaded.tzinfo is None:
        raise ValueError("Cache timestamp has no timezone.")

    age = (datetime.now(timezone.utc) - downloaded).total_seconds()
    if age < 0:
        raise ValueError("Cache timestamp is in the future.")

    return age


def load_scorer():
    previous_scorer = None
    previous_age = None

    try:
        previous_age = read_cache_age()
        previous_scorer = PickScorer()

        # Ensure every mapped hero has baseline statistics.
        missing = (
            set(previous_scorer.hero_ids.values())
            - previous_scorer.overall.keys()
        )
        if missing:
            previous_scorer = None
            raise ValueError(f"Missing overall statistics for IDs: {missing}")

    except CACHE_ERRORS as error:
        print(f"Statistics cache unavailable: {error}")

    if previous_scorer is not None and previous_age < MAX_AGE_SECONDS:
        print(f"Using cached statistics ({previous_age / 60:.0f} minutes old).")
        return previous_scorer

    print("Refreshing statistics before capture starts...", flush=True)

    try:
        update_stats()
        read_cache_age()
        scorer = PickScorer()

        missing = set(scorer.hero_ids.values()) - scorer.overall.keys()
        if missing:
            raise ValueError(f"Missing overall statistics for IDs: {missing}")

        print("Fresh statistics ready.")
        return scorer

    except (httpx.HTTPError, *CACHE_ERRORS) as error:
        print(f"Statistics refresh failed: {error}")

        if previous_scorer is not None:
            print(
                "Using previously loaded statistics "
                f"({previous_age / 3600:.1f} hours old)."
            )
            return previous_scorer

        print("Recommendations disabled. Screen detection will still run.")
        return None