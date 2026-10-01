"""Bundled demo data: three teammates, 15 days, one challenge.

Profiles (deterministic, seeded RNG):
  sam    car-heavy commuter   (transport dominates)
  priya  electric-heat home   (home energy dominates)
  leo    frequent flyer + beef-heavy diet (diet/transport)

Baseline window: 7 days before the challenge, slightly higher footprints.
Challenge window: 7 days up to `today`, with each member cutting ~15-25%,
so the leaderboard shows real reductions out of the box.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from . import db

USERS = ("sam", "priya", "leo")


def _day_range(end: date, n: int):
    return [end - timedelta(days=i) for i in range(n - 1, -1, -1)]


def seed_demo(conn, today: date | None = None) -> dict:
    """Insert demo activities + a demo challenge. Returns a summary dict."""
    today = today or date.today()
    db.init_db(conn)
    rng = random.Random(42)

    baseline_days = _day_range(today - timedelta(days=8), 7)   # -14..-8
    challenge_days = _day_range(today, 8)                       # -7..0

    def add(user, day, category, detail, amount):
        jitter = 1 + rng.uniform(-0.08, 0.08)
        db.log_activity(conn, user=user, date=day.isoformat(),
                        category=category, detail=detail,
                        amount=round(amount * jitter, 2))

    for day in baseline_days:
        wd = day.weekday() < 5  # commute only on weekdays
        # sam: drives 32 km every weekday
        if wd:
            add("sam", day, "transport", "car_gasoline", 32)
        add("sam", day, "energy", "grid", 9)
        add("sam", day, "diet", "chicken" if wd else "vegetarian", 2)
        # priya: bus commuter, electric heating
        if wd:
            add("priya", day, "transport", "bus", 14)
        add("priya", day, "energy", "grid", 26)
        add("priya", day, "diet", "vegetarian", 2)
        add("priya", day, "diet", "fish", 1)
        # leo: drives + flies + beef
        if wd:
            add("leo", day, "transport", "car_gasoline", 18)
        add("leo", day, "transport", "flight_short", 60 if wd else 0)
        add("leo", day, "energy", "natural_gas", 12)
        add("leo", day, "diet", "beef", 1)
        add("leo", day, "diet", "pork", 1)

    for day in challenge_days:
        wd = day.weekday() < 5
        # sam: buses twice a week now (-25% car km), shorter showers
        if wd:
            add("sam", day, "transport", "car_gasoline", 24)
            if day.weekday() in (1, 3):
                add("sam", day, "transport", "bus", 32)
        add("sam", day, "energy", "grid", 8)
        add("sam", day, "diet", "chicken" if wd else "vegetarian", 2)
        # priya: turned the thermostat down (-20% energy)
        if wd:
            add("priya", day, "transport", "bus", 14)
        add("priya", day, "energy", "grid", 21)
        add("priya", day, "diet", "vegetarian", 2)
        add("priya", day, "diet", "fish", 1)
        # leo: one beef meal swapped for chicken, fewer flights
        if wd:
            add("leo", day, "transport", "car_gasoline", 15)
        add("leo", day, "transport", "flight_short", 30 if wd else 0)
        add("leo", day, "energy", "natural_gas", 11)
        add("leo", day, "diet", "beef", 1 if day.weekday() % 2 else 0)
        add("leo", day, "diet", "chicken", 1 if not day.weekday() % 2 else 0)
        add("leo", day, "diet", "pork", 1)

    challenge_id = db.create_challenge(
        conn,
        name="October Carbon Cut (-10%)",
        target_pct=10.0,
        start_date=(today - timedelta(days=7)).isoformat(),
        end_date=today.isoformat(),
        baseline_days=7,
    )
    for user in USERS:
        db.join_challenge(conn, challenge_id=challenge_id, user=user)

    return {"users": list(USERS), "challenge_id": challenge_id,
            "challenge": "October Carbon Cut (-10%)"}
