"""Offline public-data evaluation. Never changes the live app or its caches.

Run from the project root: python tools/evaluate_competitive.py
Dependencies: numpy, scikit-learn (no game or personal account required).
"""
import argparse
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

BASE = "https://api.deadlock-api.com"
VERSION = 1
PRIORS = (100, 500, 2000)
REGULARIZATION = (0.01, 0.1, 1.0)


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


class PublicAPI:
    def __init__(self, cache):
        self.cache = cache
        self.last_request = 0.0

    def get(self, endpoint, params):
        identity = json.dumps([endpoint, params], sort_keys=True)
        key = hashlib.sha256(identity.encode()).hexdigest()
        path = self.cache / (key + ".json")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
        for attempt in range(3):
            time.sleep(max(0, 2.2 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            request = urllib.request.Request(url, headers={
                "User-Agent": "DeadlockCompanion-offline-evaluation/1",
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    value = json.load(response)
                if not isinstance(value, list):
                    raise ValueError(f"{endpoint}: expected a JSON list")
                save_json(path, value)
                return value
            except urllib.error.HTTPError as error:
                if error.code not in (429, 502, 503, 504) or attempt == 2:
                    raise
                retry = error.headers.get("Retry-After", "5")
                delay = float(retry) if retry.isdigit() else 5
                if delay > 30:
                    raise RuntimeError(f"API requests a {delay:g}s wait. Retry later.") from error
                print(f"API busy ({error.code}); retrying in {max(3, delay):g}s...", flush=True)
                time.sleep(max(3, delay))


def winner_label(value):
    # Team0 / 0 -> label 1 (Team0 wins); Team1 / 1 -> label 0.
    if isinstance(value, bool):
        return None
    if value in ("Team0", 0):
        return 1
    if value in ("Team1", 1):
        return 0
    return None


def validate_rows(rows, fields, count_field):
    if not rows:
        raise ValueError("Empty historical statistics response")
    seen = set()
    for row in rows:
        key = tuple(row[field] for field in fields)
        if len(fields) == 2 and fields[0] == "hero_id1":
            key = tuple(sorted(key))
        if key in seen:
            raise ValueError(f"Duplicate historical record: {key}")
        seen.add(key)
        n, w = row[count_field], row["wins"]
        if type(n) is not int or type(w) is not int or n <= 0 or not 0 <= w <= n:
            raise ValueError("Invalid historical win/match counts")


class PairFeatures:
    def __init__(self, overall, counters, synergies):
        validate_rows(overall, ("hero_id",), "matches")
        validate_rows(counters, ("hero_id", "enemy_hero_id"), "matches_played")
        validate_rows(synergies, ("hero_id1", "hero_id2"), "matches_played")
        self.base = {r["hero_id"]: r["wins"] / r["matches"] for r in overall}
        # Preserve both directions exactly as reported by the API.
        self.counter = {}
        for r in counters:
            a, b = r["hero_id"], r["enemy_hero_id"]
            if a == b or a not in self.base or b not in self.base:
                continue
            self.counter[(a, b)] = (r["wins"], r["matches_played"])

        for a, b in self.counter:
            if (b, a) not in self.counter:
                raise ValueError(
                    f"Missing reverse counter statistics: {(a, b)}"
                )
        self.synergy = {}
        for r in synergies:
            a, b = r["hero_id1"], r["hero_id2"]
            if a != b and a in self.base and b in self.base:
                self.synergy[tuple(sorted((a, b)))] = (r["wins"], r["matches_played"])
        self.counter_beta = self.fit_beta(self.counter, False)
        self.synergy_beta = self.fit_beta(self.synergy, True)

    def fit_beta(self, pairs, allied):
        numerator = denominator = 0.0
        for (a, b), (w, n) in pairs.items():
            x = self.base[a] + self.base[b] - 1 if allied else self.base[a] - self.base[b]
            numerator += n * x * (w / n - 0.5)
            denominator += n * x * x
        if denominator < 1e-12:
            return 0.0
        return numerator / denominator

    def effect(self, a, b, allied, prior, fitted):
        pairs = self.synergy if allied else self.counter
        key = tuple(sorted((a, b))) if allied else (a, b)

        if key not in pairs:
            return 0.0

        w, n = pairs[key]
        observed = w / n
        beta = (
            self.synergy_beta if allied else self.counter_beta
        ) if fitted else 1.0

        x = (
            self.base[a] + self.base[b] - 1
            if allied
            else self.base[a] - self.base[b]
        )
        expected = min(1.0, max(0.0, 0.5 + beta * x))
        return (observed - expected) * n / (n + prior)

    def vector(self, match, prior=500, fitted=True):
        a, b = match["team0"], match["team1"]
        strength = sum(self.base[h] for h in a) - sum(self.base[h] for h in b)
        counter = sum(
            self.effect(x, y, False, prior, fitted)
            - self.effect(y, x, False, prior, fitted)
            for x in a for y in b
        )
        def allies(team):
            return sum(self.effect(team[i], team[j], True, prior, fitted)
                       for i in range(6) for j in range(i + 1, 6))
        # Each player's enemy effect is averaged over six opponents.
        # Allied pairs appear in two players' scores, each divided by five.
        return np.array([
            strength,
            counter / 6,
            (allies(a) - allies(b)) * 2 / 5,
        ]) * 100


def fit_model(x, y, c):
    # Side-symmetric model: swapping the teams flips the probability.
    model = make_pipeline(StandardScaler(with_mean=False), LogisticRegression(
        C=c, fit_intercept=False, max_iter=2000, solver="lbfgs"))
    model.fit(x, y)
    return model


def metrics(y, p):
    return {"log_loss": float(log_loss(y, p, labels=[0, 1])),
            "brier": float(brier_score_loss(y, p)),
            "auc": float(roc_auc_score(y, p)),
            "accuracy": float(np.mean((p >= .5) == y))}


def bootstrap_gain(y, baseline, candidate, windows):
    # Resample whole collection windows, not individual correlated matches.
    def losses(p):
        p = np.clip(p, 1e-12, 1 - 1e-12)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))
    difference = losses(baseline) - losses(candidate)
    groups = [np.flatnonzero(windows == w) for w in np.unique(windows)]
    rng = np.random.default_rng(51923)
    gains = []
    for _ in range(2000):
        indices = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        gains.append(float(difference[indices].mean()))
    return [float(x) for x in np.quantile(gains, [.025, .975])]


def run(root):
    source_path = root / "data" / "real_lineups.json"
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    for match in source["lineups"]:
        value = match["start_time"]

        if isinstance(value, str):
            value = value.strip()
            try:
                timestamp = float(value)
            except ValueError:
                parsed = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                timestamp = parsed.timestamp()
        elif type(value) in (int, float):
            timestamp = float(value)
        else:
            raise ValueError(f"Invalid start_time: {value!r}")

        if not math.isfinite(timestamp):
            raise ValueError(f"Invalid start_time: {value!r}")

        match["start_time"] = timestamp
    windows = sorted(source["sampling"]["windows"])
    if len(windows) < 20:
        raise ValueError("Need at least 20 collection windows for this evaluation")
    count = len(windows)
    first = int(count * .4)
    second = int(count * .65) - 1
    third = int(count * .8)
    # Four chronological blocks. All baseline/pair data end before model fit.
    fit_start = windows[first][0]
    tune_start = windows[second][0]
    test_start = windows[third][0]
    print(f"Windows: statistics {first}, fit {second-first}, tune {third-second}, test {count-third}")
    print("Fetching historical aggregate statistics (separate from live caches)...", flush=True)
    output = root / "data" / "competitive_evaluation"
    api = PublicAPI(output / "requests")
    params = {**source["filters"], "max_unix_timestamp": fit_start - 1}
    overall = api.get("/v1/analytics/hero-stats", {**params, "bucket": "no_bucket"})
    pair_params = {**params, "same_lane_filter": "false", "min_matches": 1}
    counters = api.get("/v1/analytics/hero-counter-stats", pair_params)
    synergies = api.get("/v1/analytics/hero-synergy-stats", pair_params)
    features = PairFeatures(overall, counters, synergies)

    samples = [m for m in source["lineups"] if m["start_time"] >= fit_start]
    mapping = json.loads(
        (root / "hero_ids.json").read_text(encoding="utf-8")
    )
    names = {int(hero_id): name for name, hero_id in mapping.items()}

    missing_heroes = Counter(
        hero
        for match in samples
        for hero in set(match["team0"] + match["team1"])
        if hero not in features.base
    )

    print("\nHeroes missing from historical statistics:")
    for hero, count in missing_heroes.most_common():
        print(
            f"  {names.get(int(hero), 'unknown')} "
            f"(ID {hero!r}, type {type(hero).__name__}): "
            f"{count:,} matches"
        )

    print(
        "Historical hero ID types:",
        sorted({type(hero).__name__ for hero in features.base}),
    )
    ids = sorted(m["match_id"] for m in samples)
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate match IDs in source")
    labels = {}
    skipped = Counter()
    for offset in range(0, len(ids), 500):
        print(f"Fetching public winners: {offset:,}/{len(ids):,}...", flush=True)
        rows = api.get("/v1/matches/metadata", {
            "match_ids": ",".join(str(i) for i in ids[offset:offset+500]),
            "limit": 500, "include_info": "true", "include_player_info": "false",
            "game_mode": "normal", "match_mode": "ranked",
        })
        for m in rows:
            winner = winner_label(m.get("winning_team"))
            if winner is None:
                skipped["unrecognised_winner:" + str(m.get("winning_team"))] += 1
            elif m.get("not_scored") not in (False, 0):
                skipped["unscored_or_unknown_scored_status"] += 1
            else:
                labels[m["match_id"]] = winner

    matches, outcomes, window_ids = [], [], []
    for m in sorted(samples, key=lambda x: (x["start_time"], x["match_id"])):
        if m["match_id"] not in labels:
            skipped["source_match_without_usable_label"] += 1
            continue
        all_heroes = m["team0"] + m["team1"]
        if len(m["team0"]) != 6 or len(m["team1"]) != 6 or len(set(all_heroes)) != 12:
            raise ValueError("Invalid 6v6 lineup")
        if not set(all_heroes) <= features.base.keys():
            skipped["hero_unseen_in_historical_statistics"] += 1
            continue
        matching_windows = [i for i, (a, b) in enumerate(windows) if a <= m["start_time"] < b]
        if len(matching_windows) != 1:
            raise ValueError("Match outside collection windows, or overlapping windows")
        matches.append(m)
        outcomes.append(labels[m["match_id"]])
        window_ids.append(matching_windows[0])

    y = np.array(outcomes)
    stamps = np.array([m["start_time"] for m in matches])

    # Split eligible pre-test matches chronologically.
    # Keep the original final test period untouched.
    pretest_stamps = np.sort(stamps[stamps < test_start])

    if len(pretest_stamps) < 800:
        raise ValueError(
            "Need at least 800 eligible pre-test matches "
            "for this 75/25 split."
        )

    boundary = int(len(pretest_stamps) * 0.75)
    tune_start = float(pretest_stamps[boundary])

    masks = [
        stamps < tune_start,
        (stamps >= tune_start) & (stamps < test_start),
        stamps >= test_start,
    ]
    print("Usable matches (fit / tune / test):", [int(mask.sum()) for mask in masks])
    print("Exclusions:", dict(skipped))
    for mask in masks:
        if mask.sum() < 200 or len(set(y[mask])) != 2:
            raise ValueError("Insufficient matches or both outcomes not present in every split")

    matrices = {prior: np.array([features.vector(m, prior) for m in matches]) for prior in PRIORS}
    old = np.array([features.vector(m, 500, False).sum() for m in matches])[:, None]
    specs = {
        "Overall only": [(0, matrices[500][:, :1])],
        "Existing equal weights": [(500, old)],
        "Fit overall + enemies": [(p, x[:, [0, 1]]) for p, x in matrices.items()],
        "Fit overall + allies": [(p, x[:, [0, 2]]) for p, x in matrices.items()],
        "Fit all three": list(matrices.items()),
    }
    selected, report = {}, {}
    fit_mask, tune_mask, test_mask = masks
    for name, candidates in specs.items():
        best = None
        for prior, x in candidates:
            for c in REGULARIZATION:
                model = fit_model(x[fit_mask], y[fit_mask], c)
                loss = log_loss(y[tune_mask], model.predict_proba(x[tune_mask])[:, 1], labels=[0, 1])
                if best is None or loss < best[0]:
                    best = (loss, prior, c, model, x)
        loss, prior, c, model, x = best
        # No refitting or model selection using the test outcomes.
        p = model.predict_proba(x[test_mask])[:, 1]
        selected[name] = (loss, p)
        scale = model.named_steps["standardscaler"].scale_
        coefficients = model.named_steps["logisticregression"].coef_[0] / scale
        report[name] = {"tuning_log_loss": float(loss), "prior": prior, "C": c,
                        "coefficients": coefficients.tolist(), "test": metrics(y[test_mask], p)}

    # Choose challenger on tuning data only; then inspect its held-out result.
    challenger = min((n for n in selected if n.startswith("Fit ")), key=lambda n: selected[n][0])
    baseline = selected["Overall only"][1]
    candidate = selected[challenger][1]
    interval = bootstrap_gain(y[test_mask], baseline, candidate, np.array(window_ids)[test_mask])
    print("\nHELD-OUT PUBLIC-MATCH RESULTS (lower log loss/Brier is better)")
    print(f"{'Model':28} {'Log loss':>10} {'Brier':>9} {'AUC':>8} {'Accuracy':>10}")
    for name, record in report.items():
        m = record["test"]
        print(f"{name:28} {m['log_loss']:10.5f} {m['brier']:9.5f} {m['auc']:8.3f} {100*m['accuracy']:9.2f}%")
    gain = report["Overall only"]["test"]["log_loss"] - report[challenger]["test"]["log_loss"]
    print(f"\nChallenger selected BEFORE testing: {challenger}")
    print(f"Log-loss improvement over overall only: {gain:+.5f}")
    print(f"Approximate 95% window-bootstrap interval: [{interval[0]:+.5f}, {interval[1]:+.5f}]")
    print("Caution: only a few held-out time windows; uncertainty estimates are preliminary.")
    if interval[0] > 0:
        print("Interaction model improved this held-out sample. Check another period before deployment.")
    else:
        print("No clear improvement established in this sample. Do not automatically increase the weights.")
    print("This tests team-outcome prediction, not the causal benefit of changing heroes.")
    print("Live app settings and caches were NOT modified.")
    save_json(output / "report.json", {
        "version": VERSION, "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "historical_filters": params, "fit_start": fit_start, "tune_start": tune_start,
        "test_start": test_start, "split_counts": [int(m.sum()) for m in masks],
        "test_windows": int(len(np.unique(np.array(window_ids)[test_mask]))),
        "exclusions": dict(skipped), "counter_beta": features.counter_beta,
        "synergy_beta": features.synergy_beta, "models": report,
        "chosen_challenger": challenger, "improvement_interval": interval,
    })
    print(f"Saved {output / 'report.json'}")


def self_test():
    assert winner_label("Team0") == 1 and winner_label("Team1") == 0
    assert winner_label(0) == 1 and winner_label(1) == 0
    assert winner_label(True) is None and winner_label("unknown") is None
    overall = [{"hero_id": h, "wins": 500 + h, "matches": 1000} for h in range(12)]
    counters, synergies = [], []
    for a in range(12):
        for b in range(a + 1, 12):
            w = 450 + (a * 7 + b * 3) % 100
            counters.extend([{"hero_id": a, "enemy_hero_id": b, "wins": w, "matches_played": 1000},
                             {"hero_id": b, "enemy_hero_id": a, "wins": 1000-w, "matches_played": 1000}])
            synergies.append({"hero_id1": a, "hero_id2": b, "wins": w, "matches_played": 1000})
    f = PairFeatures(overall, counters, synergies)
    m = {"team0": list(range(6)), "team1": list(range(6, 12))}
    reverse = {"team0": m["team1"], "team1": m["team0"]}
    for fitted in (True, False):
        assert np.allclose(f.vector(m, fitted=fitted), -f.vector(reverse, fitted=fitted))
        reordered = {k: v[::-1] for k, v in m.items()}
        assert np.allclose(f.vector(m, fitted=fitted), f.vector(reordered, fitted=fitted))
    rng = np.random.default_rng(42)
    x = rng.normal(size=(1000, 3))
    p = 1 / (1 + np.exp(-x[:, 0]))
    y = (rng.random(1000) < p).astype(int)
    model = fit_model(x[:600], y[:600], .1)
    assert np.allclose(model.predict_proba(x[600:])[:, 1] + model.predict_proba(-x[600:])[:, 1], 1)
    result = metrics(y[600:], model.predict_proba(x[600:])[:, 1])
    assert all(math.isfinite(v) for v in result.values())
    print("PASS: winner parsing, pair validation, team symmetry, lane-order invariance, and model fitting.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            run(Path(__file__).resolve().parents[1])
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        import traceback
        traceback.print_exc()
        raise SystemExit("Evaluation stopped. Live app files were not changed.")
