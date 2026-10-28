from app_paths import DATA_DIR
import hashlib
import json
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import httpx

from scoring import PRIOR_MATCHES, MATCHUP_WEIGHT, SYNERGY_WEIGHT
from tools.download_real_lineups import main as download_lineups

ROOT = Path(__file__).resolve().parent
LINEUPS = DATA_DIR / "real_lineups.json"
CACHE = DATA_DIR / "real_opportunity_cache.json"

LINEUP_MAX_AGE_SECONDS = 24 * 60 * 60
REFERENCE_VERSION = 1


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def age_seconds(timestamp):
    downloaded = datetime.fromisoformat(timestamp)
    if downloaded.tzinfo is None:
        raise ValueError("Reference timestamp has no timezone.")

    age = (datetime.now(timezone.utc) - downloaded).total_seconds()
    if age < 0:
        raise ValueError("Reference timestamp is in the future.")
    return age


class RealOpportunityScorer:
    def __init__(self, scorer):
        source = None

        try:
            source = read_json(LINEUPS)
            source_age = age_seconds(source["downloaded_at"])
            if not source.get("lineups"):
                raise ValueError("Recorded lineup dataset is empty.")
        except (OSError, ValueError, KeyError, TypeError):
            source = None
            source_age = float("inf")

        if source_age >= LINEUP_MAX_AGE_SECONDS:
            print("Refreshing recorded lineups...", flush=True)

            try:
                download_lineups()
                source = read_json(LINEUPS)
                source_age = age_seconds(source["downloaded_at"])
            except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError):
                if source is None:
                    raise
                print(
                    "Lineup refresh failed; using previous recorded lineups "
                    f"({source_age / 3600:.1f} hours old).",
                    flush=True,
                )

        if source is None or not source.get("lineups"):
            raise ValueError("No usable recorded lineups.")

        stats_bytes = (DATA_DIR / "hero_stats.json").read_bytes()
        stats = json.loads(stats_bytes)

        if stats["downloaded_at"] != scorer.downloaded_at:
            raise ValueError(
                "Loaded statistics differ from the file. Restart the app."
            )

        # Date windows may differ because lineups refresh daily and
        # statistics refresh hourly. Other population filters must match.
        excluded = {"min_unix_timestamp", "max_unix_timestamp"}

        def population_filters(filters):
            return {
                key: value for key, value in filters.items()
                if key not in excluded
            }

        if population_filters(source["filters"]) != population_filters(
            stats["filters"]
        ):
            raise ValueError("Lineup and statistics population filters differ.")

        source_bytes = json.dumps(
            source, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        identity = {
            "version": REFERENCE_VERSION,
            "stats_sha256": hashlib.sha256(stats_bytes).hexdigest(),
            "lineups_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "hero_ids": scorer.hero_ids,
            "prior_matches": PRIOR_MATCHES,
            "matchup_weight": MATCHUP_WEIGHT,
            "synergy_weight": SYNERGY_WEIGHT,
        }

        try:
            cached = read_json(CACHE)
        except (OSError, ValueError):
            cached = {}

        references = cached.get("references")
        usable = (
            cached.get("identity") == identity
            and isinstance(references, dict)
            and set(references) == set(scorer.hero_ids)
            and all(
                isinstance(entry, dict)
                and entry.get("count", 0) > 0
                and len(entry.get("sorted_adjustments", []))
                == entry["count"]
                and isinstance(entry.get("mean_adjustment"), (int, float))
                for entry in references.values()
            )
        )

        if usable:
            print("Using cached real-match opportunity references.", flush=True)
        else:
            print("Building real-match opportunity references...", flush=True)
            references = self.build(scorer, source["lineups"])

            # Avoid saving references if another process replaced the stats.
            current_bytes = (DATA_DIR / "hero_stats.json").read_bytes()
            if hashlib.sha256(current_bytes).hexdigest() != identity["stats_sha256"]:
                raise ValueError("Statistics changed during the build.")

            cached = {
                "identity": identity,
                "references": references,
                "built_at": datetime.now(timezone.utc).isoformat(),
            }

            CACHE.parent.mkdir(parents=True, exist_ok=True)
            temporary = CACHE.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(cached, indent=2),
                encoding="utf-8",
            )
            temporary.replace(CACHE)

        self.references = references
        self.downloaded_at = source["downloaded_at"]
        self.filters = source["filters"]

    @staticmethod
    def build(scorer, lineups):
        names = {
            hero_id: name for name, hero_id in scorer.hero_ids.items()
        }
        effects = {hero: [] for hero in scorer.hero_ids}
        seen = set()

        for match in lineups:
            match_id = match["match_id"]
            if match_id in seen:
                raise ValueError(f"Duplicate recorded match: {match_id}")
            seen.add(match_id)

            team0 = [names[value] for value in match["team0"]]
            team1 = [names[value] for value in match["team1"]]

            if (
                len(team0) != 6
                or len(team1) != 6
                or len(set(team0 + team1)) != 12
            ):
                raise ValueError(f"Invalid recorded lineup: {match_id}")

            for allies, enemies in ((team0, team1), (team1, team0)):
                for hero in allies:
                    teammates = [ally for ally in allies if ally != hero]
                    result = scorer.score(hero, teammates, enemies)

                    if result["missing"]:
                        raise ValueError(f"Missing pair statistics for {hero}")

                    effects[hero].append(
                        result["matchup_points"] + result["synergy_points"]
                    )

        references = {}
        for hero, values in effects.items():
            if not values:
                raise ValueError(f"No recorded reference matches for {hero}")

            references[hero] = {
                "count": len(values),
                "mean_adjustment": mean(values),
                "sorted_adjustments": sorted(round(value, 8) for value in values),
            }

        print(f"Built references from {len(seen):,} recorded matches.", flush=True)
        return references

    def describe(self, result):
        reference = self.references[result["hero"]]
        effect = result["matchup_points"] + result["synergy_points"]
        values = reference["sorted_adjustments"]
        rounded = round(effect, 8)

        below = bisect_left(values, rounded)
        below_or_equal = bisect_right(values, rounded)

        return {
            "opportunity_percentile": (
                100 * (below + below_or_equal) / (2 * len(values))
            ),
            "above_typical_points": effect - reference["mean_adjustment"],
            "opportunity_reference_count": reference["count"],
            "opportunity_reference_downloaded_at": self.downloaded_at,
        }