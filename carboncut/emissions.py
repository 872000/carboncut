"""Emission math: turn activity rows into kgCO2e footprints.

Every computation goes through :func:`load_factors`, whose values live in
``emission_factors.json`` and are documented estimates (see its disclaimer).
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FACTORS_PATH = os.path.join(os.path.dirname(HERE), "emission_factors.json")


def load_factors(path: str | None = None) -> dict:
    """Load the emission-factors document (JSON)."""
    with open(path or DEFAULT_FACTORS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def factor_for(factors: dict, category: str, detail: str) -> float:
    """Return the kgCO2e factor for one activity type.

    Raises KeyError with a helpful message listing valid details.
    """
    try:
        entry = factors[category]["factors"][detail]
    except KeyError:
        valid = sorted(factors.get(category, {}).get("factors", {}))
        raise KeyError(
            f"unknown {category} detail {detail!r}; "
            f"valid options: {', '.join(valid) or '(none)'}"
        )
    return float(entry["factor"])


def activity_co2e(activity, factors: dict) -> float:
    """kgCO2e for a single activity row (amount x factor)."""
    return float(activity["amount"]) * factor_for(
        factors, activity["category"], activity["detail"]
    )


def summarize(rows, factors: dict) -> dict:
    """Aggregate activity rows into totals, by category, by day and by detail."""
    total = 0.0
    by_category: dict[str, float] = {}
    by_day: dict[str, float] = {}
    by_detail: dict[str, float] = {}
    for row in rows:
        co2e = activity_co2e(row, factors)
        total += co2e
        cat = row["category"]
        by_category[cat] = by_category.get(cat, 0.0) + co2e
        day = row["date"]
        by_day[day] = by_day.get(day, 0.0) + co2e
        key = f"{cat}:{row['detail']}"
        by_detail[key] = by_detail.get(key, 0.0) + co2e
    return {
        "total": total,
        "by_category": by_category,
        "by_day": dict(sorted(by_day.items())),
        "by_detail": by_detail,
    }
