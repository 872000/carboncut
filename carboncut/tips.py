"""Rule-based reduction suggestions.

Tips are driven by the user's *top emission categories* over a trailing
window: the engine finds which category (and which detail inside it) dominates
the footprint and proposes the highest-leverage swap for that profile, with
an estimated weekly saving computed from the user's own numbers.

All savings are estimates derived from ``emission_factors.json`` - the same
documented-estimate factors used everywhere else in CarbonCut.
"""
from __future__ import annotations

from .emissions import factor_for, summarize

CAR_CATEGORIES = ("transport", "energy", "diet")


def _weekly(total: float, days: int) -> float:
    return total / max(days, 1) * 7.0


def _tip(title: str, why: str, action: str, savings: float,
         category: str) -> dict:
    return {
        "title": title,
        "why": why,
        "action": action,
        "estimated_savings_kg_per_week": round(max(savings, 0.0), 2),
        "category": category,
    }


def generate_tips(rows, factors: dict, days: int = 30, top_n: int = 5) -> list[dict]:
    """Return up to `top_n` tips, sorted by estimated weekly saving (desc)."""
    summary = summarize(rows, factors)
    total = summary["total"]
    by_cat = summary["by_category"]
    by_detail = summary["by_detail"]

    generic = [
        _tip(
            "Log every day for a week",
            "You can't cut what you don't measure - a full week of data "
            "makes every other tip sharper.",
            "Use `carboncut log` daily; then re-run `carboncut tips`.",
            0.0, "general",
        ),
        _tip(
            "One car-free day a week",
            "Transport is the easiest category to move with a single habit.",
            "Pick a day, leave the keys at home, walk/bike/bus instead.",
            _weekly(by_detail.get("transport:car_gasoline", 0.0)
                     + by_detail.get("transport:car_diesel", 0.0), days) / 7.0,
            "transport",
        ),
    ]
    if total <= 0:
        return generic

    shares = {c: by_cat.get(c, 0.0) / total for c in CAR_CATEGORIES}
    tips: list[dict] = []

    # --- 1. Car-heavy commuter -> transit ---------------------------------
    car_kg = (by_detail.get("transport:car_gasoline", 0.0)
              + by_detail.get("transport:car_diesel", 0.0)
              + by_detail.get("transport:car_hybrid", 0.0))
    if shares["transport"] >= 0.35 and car_kg > 0:
        car_f = factor_for(factors, "transport", "car_gasoline")
        bus_f = factor_for(factors, "transport", "bus")
        # swap 30% of car-km to bus each week
        savings = _weekly(car_kg, days) * 0.30 * (1 - bus_f / car_f)
        tips.append(_tip(
            "Swap 2 car commutes a week for the bus",
            f"Cars are {shares['transport']:.0%} of your footprint.",
            "Take the bus/train for ~30% of your weekly car kilometres.",
            savings, "transport",
        ))

    # --- 2. Grid-electricity-heavy home -> cut 10% -------------------------
    grid_kg = by_detail.get("energy:grid", 0.0)
    if shares["energy"] >= 0.30 and grid_kg > 0:
        savings = _weekly(grid_kg, days) * 0.10
        tips.append(_tip(
            "Trim 10% of grid electricity",
            f"Home energy is {shares['energy']:.0%} of your footprint.",
            "LEDs, cold-water laundry, and killing standby loads typically "
            "save ~10% with zero lifestyle change.",
            savings, "energy",
        ))
        green_f = factor_for(factors, "energy", "green_tariff")
        grid_f = factor_for(factors, "energy", "grid")
        grid_kwh_week = _weekly(grid_kg, days) / grid_f
        tips.append(_tip(
            "Switch to a green electricity tariff",
            "Same sockets, cleaner electrons.",
            "A certified renewable tariff cuts electricity emissions by "
            f"~{(1 - green_f / grid_f):.0%}.",
            grid_kwh_week * (grid_f - green_f), "energy",
        ))

    # --- 3. Beef-heavy diet -> chicken/veg swaps ---------------------------
    beef_kg = by_detail.get("diet:beef", 0.0)
    beef_f = factor_for(factors, "diet", "beef")
    chicken_f = factor_for(factors, "diet", "chicken")
    beef_meals_week = _weekly(beef_kg, days) / beef_f if beef_f else 0.0
    if shares["diet"] >= 0.25 and beef_meals_week >= 1:
        n = max(1, min(2, int(beef_meals_week)))
        tips.append(_tip(
            f"Swap {n} beef meal{'s' if n > 1 else ''} a week for chicken",
            f"Diet is {shares['diet']:.0%} of your footprint and beef "
            "dominates it (ruminant methane).",
            "Chicken or vegetarian versions of the same dishes.",
            n * (beef_f - chicken_f), "diet",
        ))

    # --- 4. Flights -> fewer / rail ---------------------------------------
    flight_kg = (by_detail.get("transport:flight_short", 0.0)
                 + by_detail.get("transport:flight_long", 0.0))
    if flight_kg > 0:
        short_f = factor_for(factors, "transport", "flight_short")
        train_f = factor_for(factors, "transport", "train")
        # assume the short-haul km could move to rail: saving per kg ratio
        tips.append(_tip(
            "Take the train for your next short trip",
            "One short flight can outweigh weeks of careful daily habits.",
            "For trips under ~800 km, rail emits roughly "
            f"{train_f / short_f:.0%} of flying per km.",
            _weekly(flight_kg, days) * 0.5 * (1 - train_f / short_f),
            "transport",
        ))

    tips.extend(generic)
    # de-duplicate by title, keep highest saving, then sort
    seen: dict[str, dict] = {}
    for t in tips:
        if (t["title"] not in seen
                or t["estimated_savings_kg_per_week"]
                > seen[t["title"]]["estimated_savings_kg_per_week"]):
            seen[t["title"]] = t
    ordered = sorted(seen.values(),
                     key=lambda t: t["estimated_savings_kg_per_week"],
                     reverse=True)
    return ordered[:top_n]


def format_tips(tips: list[dict]) -> str:
    lines = ["Your top reduction opportunities (est. kgCO2e / week):", ""]
    for i, t in enumerate(tips, 1):
        lines.append(
            f"{i}. {t['title']}  (~{t['estimated_savings_kg_per_week']} kg/wk)")
        lines.append(f"   Why: {t['why']}")
        lines.append(f"   Do:  {t['action']}")
        lines.append("")
    return "\n".join(lines).rstrip()
