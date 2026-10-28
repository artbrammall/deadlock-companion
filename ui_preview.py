"""Example data only. Never start capture or use the real history database."""
from datetime import datetime, timezone, timedelta


def example_lineup():
    downloaded = (datetime.now(timezone.utc) - timedelta(minutes=46)).isoformat()
    rows = []
    for hero, baseline, enemy, ally, percentile, above in (
        ('haze', 52.07, -0.19, -0.11, 96.9, 0.657),
        ('wraith', 53.10, -0.24, -0.36, 88.9, 0.536),
        ('dynamo', 51.31, 0.10, 0.07, 79.0, 0.481),
        ('grey_talon', 45.14, -0.11, -0.01, 40.0, -0.12),
        ('baba', 55.25, 0.70, -0.21, 72.0, 0.30),
    ):
        rows.append(dict(hero=hero, score=round(baseline+enemy+ally, 2), baseline_pct=baseline,
            matchup_points=enemy, synergy_points=ally, missing=[], opportunity_percentile=percentile,
            above_typical_points=above, opportunity_reference_count=2610,
            opportunity_reference_downloaded_at=downloaded))
    return dict(type='lineup', current_hero='grey_talon', self_slot=2,
                allies=['rem','abrams','grey_talon','violet','paradox','ivy'],
                enemies=['solomon','nurse_harrow','viscous','bebop','calico','apollo'],
                ranked=rows, downloaded_at=downloaded, unavailable=None)
