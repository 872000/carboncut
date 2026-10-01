"""Team challenges: create, join, log, and rank by reduction vs baseline.

Scoring: each member's baseline is their mean daily kgCO2e over the
``baseline_days`` window *before* the challenge starts. Their challenge score
is the mean daily kgCO2e over the challenge window so far. Reduction % is
``(baseline - current) / baseline * 100``; the leaderboard ranks members by
reduction, highest first.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import db
from .emissions import summarize


def _parse(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def window_total(conn, factors, user: str, start: str, end: str) -> float:
    rows = db.fetch_activities(conn, user=user, start=start, end=end)
    return summarize(rows, factors)["total"]


def daily_average(conn, factors, user: str, start: str, end: str) -> float:
    """Mean daily kgCO2e over the inclusive [start, end] window."""
    days = (_parse(end) - _parse(start)).days + 1
    if days < 1:
        return 0.0
    return window_total(conn, factors, user, start, end) / days


def create(conn, factors, *, name: str, target_pct: float,
           start: str, end: str, baseline_days: int = 7) -> int:
    """Create a challenge. `factors` is accepted for API symmetry (unused)."""
    return db.create_challenge(
        conn, name=name, target_pct=target_pct,
        start_date=start, end_date=end, baseline_days=baseline_days,
    )


def join(conn, challenge_id: int, user: str) -> None:
    db.join_challenge(conn, challenge_id=challenge_id, user=user)


def leaderboard(conn, factors, challenge_id: int,
                today: date | None = None) -> list[dict]:
    """Rank members by % reduction vs baseline. Returns ranked row dicts."""
    today = today or date.today()
    ch = db.get_challenge(conn, challenge_id)
    start = _parse(ch["start_date"])
    end = min(_parse(ch["end_date"]), today)
    baseline_end = start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=int(ch["baseline_days"]) - 1)

    rows = []
    for user in db.challenge_members(conn, challenge_id):
        baseline = daily_average(
            conn, factors, user,
            baseline_start.isoformat(), baseline_end.isoformat())
        current = daily_average(
            conn, factors, user, start.isoformat(), end.isoformat())
        reduction = (baseline - current) / baseline * 100.0 if baseline > 0 else 0.0
        rows.append({
            "user": user,
            "baseline_kg_per_day": round(baseline, 2),
            "current_kg_per_day": round(current, 2),
            "reduction_pct": round(reduction, 1),
            "hit_target": reduction >= float(ch["target_pct"]),
        })
    rows.sort(key=lambda r: r["reduction_pct"], reverse=True)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return rows
