"""Emission-math tests: known inputs -> known outputs."""
import pytest

from carboncut import db
from carboncut.emissions import (
    activity_co2e,
    factor_for,
    load_factors,
    summarize,
)


@pytest.fixture()
def factors():
    return load_factors()


def _row(category, detail, amount, date="2026-09-15"):
    return {"category": category, "detail": detail,
            "amount": amount, "date": date}


def test_factor_values_are_documented_estimates(factors):
    assert factor_for(factors, "transport", "car_gasoline") == pytest.approx(0.21)
    assert factor_for(factors, "transport", "bus") == pytest.approx(0.10)
    assert factors["_meta"]["disclaimer"].lower().startswith("all factors")


def test_car_trip_math(factors):
    # 100 km by gasoline car at 0.21 kg/km = 21 kgCO2e
    assert activity_co2e(_row("transport", "car_gasoline", 100), factors) \
        == pytest.approx(21.0)


def test_bus_is_cheaper_than_car(factors):
    car = activity_co2e(_row("transport", "car_gasoline", 10), factors)
    bus = activity_co2e(_row("transport", "bus", 10), factors)
    assert bus == pytest.approx(1.0)
    assert bus < car


def test_home_energy_math(factors):
    # 10 kWh of grid electricity at 0.42 kg/kWh = 4.2 kgCO2e
    assert activity_co2e(_row("energy", "grid", 10), factors) \
        == pytest.approx(4.2)


def test_diet_math(factors):
    # 2 beef meals at 3.3 kg/meal = 6.6 kgCO2e
    assert activity_co2e(_row("diet", "beef", 2), factors) == pytest.approx(6.6)


def test_zero_amount_is_zero(factors):
    assert activity_co2e(_row("transport", "bike", 0), factors) == pytest.approx(0.0)
    assert activity_co2e(_row("transport", "walk", 50), factors) == pytest.approx(0.0)


def test_unknown_detail_raises_helpful_error(factors):
    with pytest.raises(KeyError, match="car_rocket"):
        factor_for(factors, "transport", "car_rocket")
    with pytest.raises(KeyError, match="valid options"):
        factor_for(factors, "diet", "pizza_inferno")


def test_summarize_groups_correctly(tmp_path, factors):
    conn = db.connect(str(tmp_path / "t.db"))
    db.log_activity(conn, user="me", date="2026-09-01",
                    category="transport", detail="car_gasoline", amount=100)
    db.log_activity(conn, user="me", date="2026-09-01",
                    category="energy", detail="grid", amount=10)
    db.log_activity(conn, user="me", date="2026-09-02",
                    category="diet", detail="beef", amount=1)
    rows = db.fetch_activities(conn, user="me")

    s = summarize(rows, factors)
    assert s["total"] == pytest.approx(21.0 + 4.2 + 3.3)
    assert s["by_category"]["transport"] == pytest.approx(21.0)
    assert s["by_category"]["energy"] == pytest.approx(4.2)
    assert s["by_category"]["diet"] == pytest.approx(3.3)
    assert s["by_day"]["2026-09-01"] == pytest.approx(25.2)
    assert s["by_day"]["2026-09-02"] == pytest.approx(3.3)
    assert s["by_detail"]["transport:car_gasoline"] == pytest.approx(21.0)


def test_log_activity_rejects_bad_input(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    with pytest.raises(ValueError, match="category"):
        db.log_activity(conn, date="2026-09-01", category="space",
                        detail="rocket", amount=1)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        db.log_activity(conn, date="09/01/2026", category="diet",
                        detail="beef", amount=1)
    with pytest.raises(ValueError, match=">= 0"):
        db.log_activity(conn, date="2026-09-01", category="diet",
                        detail="beef", amount=-2)
