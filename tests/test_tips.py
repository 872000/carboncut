"""Tips-engine tests: the right tip must fire for the right profile."""
from carboncut import db
from carboncut.emissions import load_factors
from carboncut.tips import format_tips, generate_tips


def _seed(conn, user, entries, days=30, start="2026-09-01"):
    from datetime import datetime, timedelta
    base = datetime.strptime(start, "%Y-%m-%d").date()
    for i in range(days):
        day = (base + timedelta(days=i)).isoformat()
        for category, detail, amount in entries:
            db.log_activity(conn, user=user, date=day,
                            category=category, detail=detail, amount=amount)


def test_car_heavy_profile_fires_transit_tip(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    factors = load_factors()
    # 30 km/day by car = 6.3 kg/day, nothing else -> transport ~100%
    _seed(conn, "me", [("transport", "car_gasoline", 30)])
    rows = db.fetch_activities(conn, user="me")

    tips = generate_tips(rows, factors, days=30)

    assert tips, "expected at least one tip"
    top = tips[0]
    assert top["category"] == "transport"
    assert "bus" in top["title"].lower() or "car" in top["title"].lower()
    assert top["estimated_savings_kg_per_week"] > 0
    # sanity: savings can't exceed the footprint itself
    weekly_total = 6.3 * 7
    assert top["estimated_savings_kg_per_week"] <= weekly_total


def test_energy_heavy_profile_fires_energy_tip(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    factors = load_factors()
    _seed(conn, "me", [("energy", "grid", 25),
                       ("transport", "bus", 5)])
    rows = db.fetch_activities(conn, user="me")

    tips = generate_tips(rows, factors, days=30)
    energy_tips = [t for t in tips if t["category"] == "energy"]
    assert energy_tips, "expected an energy tip for a grid-heavy home"
    assert any(t["estimated_savings_kg_per_week"] > 0 for t in energy_tips)


def test_beef_heavy_profile_fires_diet_tip(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    factors = load_factors()
    _seed(conn, "me", [("diet", "beef", 2),
                       ("diet", "vegetarian", 1)])
    rows = db.fetch_activities(conn, user="me")

    tips = generate_tips(rows, factors, days=30)
    diet_tips = [t for t in tips if t["category"] == "diet"]
    assert diet_tips, "expected a diet tip for a beef-heavy profile"
    assert any("beef" in t["title"].lower() for t in diet_tips)


def test_tips_sorted_by_savings_desc(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    factors = load_factors()
    _seed(conn, "me", [("transport", "car_gasoline", 30),
                       ("energy", "grid", 25),
                       ("diet", "beef", 2)])
    rows = db.fetch_activities(conn, user="me")

    tips = generate_tips(rows, factors, days=30)
    savings = [t["estimated_savings_kg_per_week"] for t in tips]
    assert savings == sorted(savings, reverse=True)


def test_empty_profile_returns_generic_tips(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    factors = load_factors()

    tips = generate_tips([], factors, days=30)
    assert len(tips) >= 1
    assert "log every day" in tips[0]["title"].lower()


def test_format_tips_is_human_readable(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    factors = load_factors()
    _seed(conn, "me", [("transport", "car_gasoline", 30)], days=7)
    rows = db.fetch_activities(conn, user="me")

    text = format_tips(generate_tips(rows, factors, days=7))
    assert "kg/wk" in text and "Why:" in text and "Do:" in text
