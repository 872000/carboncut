"""Challenge tests: leaderboard must rank by % reduction vs baseline."""
from datetime import date

import pytest

from carboncut import challenges as ch
from carboncut import db
from carboncut.emissions import load_factors

CAR = 0.21  # kgCO2e per km, gasoline car - mirrors emission_factors.json


@pytest.fixture()
def setup(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    factors = load_factors()
    # baseline window: 2026-09-13 .. 2026-09-19 (7 days)
    # challenge window: 2026-09-20 .. 2026-09-26 (7 days)
    cid = db.create_challenge(
        conn, name="Cut 10%", target_pct=10.0,
        start_date="2026-09-20", end_date="2026-09-26", baseline_days=7)
    return conn, factors, cid


def _log_week(conn, user, start_day, km_per_day):
    for i in range(7):
        db.log_activity(conn, user=user,
                        date=f"2026-09-{start_day + i:02d}",
                        category="transport", detail="car_gasoline",
                        amount=km_per_day)


def test_leaderboard_ranks_by_reduction(setup):
    conn, factors, cid = setup
    # ana: 10 kg/day -> 7 kg/day  = 30% cut
    # bob: 10 kg/day -> 9 kg/day  = 10% cut
    _log_week(conn, "ana", 13, 10 / CAR)
    _log_week(conn, "ana", 20, 7 / CAR)
    _log_week(conn, "bob", 13, 10 / CAR)
    _log_week(conn, "bob", 20, 9 / CAR)
    db.join_challenge(conn, challenge_id=cid, user="ana")
    db.join_challenge(conn, challenge_id=cid, user="bob")

    board = ch.leaderboard(conn, factors, cid, today=date(2026, 9, 26))

    assert [r["user"] for r in board] == ["ana", "bob"]
    assert [r["rank"] for r in board] == [1, 2]
    ana, bob = board
    assert ana["reduction_pct"] == pytest.approx(30.0)
    assert bob["reduction_pct"] == pytest.approx(10.0)
    assert ana["baseline_kg_per_day"] == pytest.approx(10.0)
    assert ana["current_kg_per_day"] == pytest.approx(7.0)
    assert ana["hit_target"] is True
    assert bob["hit_target"] is True  # exactly on the 10% target counts


def test_reduction_can_be_negative(setup):
    conn, factors, cid = setup
    _log_week(conn, "cara", 13, 10 / CAR)
    _log_week(conn, "cara", 20, 12 / CAR)  # footprint went UP 20%
    db.join_challenge(conn, challenge_id=cid, user="cara")

    (row,) = ch.leaderboard(conn, factors, cid, today=date(2026, 9, 26))
    assert row["reduction_pct"] == pytest.approx(-20.0)
    assert row["hit_target"] is False


def test_zero_baseline_does_not_crash(setup):
    conn, factors, cid = setup
    # dan logged nothing in the baseline week, then logged in the challenge
    _log_week(conn, "dan", 20, 5 / CAR)
    db.join_challenge(conn, challenge_id=cid, user="dan")

    (row,) = ch.leaderboard(conn, factors, cid, today=date(2026, 9, 26))
    assert row["baseline_kg_per_day"] == pytest.approx(0.0)
    assert row["reduction_pct"] == pytest.approx(0.0)


def test_join_validations(setup):
    conn, _factors, cid = setup
    db.join_challenge(conn, challenge_id=cid, user="ana")
    with pytest.raises(ValueError, match="already joined"):
        db.join_challenge(conn, challenge_id=cid, user="ana")
    with pytest.raises(KeyError):
        db.join_challenge(conn, challenge_id=999, user="ana")
    with pytest.raises(ValueError, match="target_pct"):
        db.create_challenge(conn, name="x", target_pct=150,
                            start_date="2026-09-20", end_date="2026-09-26")
