"""SQLite persistence layer for CarbonCut.

Tables:
  activities   one row per logged activity (transport / energy / diet)
  challenges   team challenges with a baseline window and a reduction target
  memberships  which users joined which challenge
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user       TEXT NOT NULL DEFAULT 'me',
    date       TEXT NOT NULL,              -- YYYY-MM-DD
    category   TEXT NOT NULL,              -- transport | energy | diet
    detail     TEXT NOT NULL,              -- e.g. car_gasoline, grid, beef
    amount     REAL NOT NULL,              -- km | kWh | meal count
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_user_date ON activities (user, date);

CREATE TABLE IF NOT EXISTS challenges (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    target_pct    REAL NOT NULL,            -- e.g. 10.0 means "-10%"
    start_date    TEXT NOT NULL,            -- YYYY-MM-DD
    end_date      TEXT NOT NULL,            -- YYYY-MM-DD
    baseline_days INTEGER NOT NULL DEFAULT 7,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_id INTEGER NOT NULL REFERENCES challenges (id) ON DELETE CASCADE,
    user         TEXT NOT NULL,
    joined_at    TEXT NOT NULL,
    UNIQUE (challenge_id, user)
);
"""

VALID_CATEGORIES = ("transport", "energy", "diet")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_date(value: str) -> str:
    """Return value unchanged if it is YYYY-MM-DD, else raise ValueError."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError(f"date must be YYYY-MM-DD, got {value!r}")
    return value


def default_db_path() -> str:
    override = os.environ.get("CARBONCUT_DB")
    if override:
        return override
    base = os.path.join(os.path.expanduser("~"), ".local", "share", "carboncut")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "carboncut.db")


def connect(path: str | None = None) -> sqlite3.Connection:
    """Open the SQLite db (creating parent dirs) and ensure the schema exists."""
    path = path or default_db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def log_activity(conn, *, user: str = "me", date: str, category: str,
                 detail: str, amount: float) -> int:
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category must be one of {VALID_CATEGORIES}, got {category!r}")
    validate_date(date)
    amount = float(amount)
    if amount < 0:
        raise ValueError("amount must be >= 0")
    cur = conn.execute(
        "INSERT INTO activities (user, date, category, detail, amount, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (user, date, category, detail, amount, utcnow()),
    )
    conn.commit()
    return cur.lastrowid


def fetch_activities(conn, *, user: str | None = None,
                     start: str | None = None, end: str | None = None):
    query = "SELECT * FROM activities WHERE 1 = 1"
    params: list = []
    if user is not None:
        query += " AND user = ?"
        params.append(user)
    if start is not None:
        query += " AND date >= ?"
        params.append(validate_date(start))
    if end is not None:
        query += " AND date <= ?"
        params.append(validate_date(end))
    query += " ORDER BY date ASC, id ASC"
    return conn.execute(query, params).fetchall()


def create_challenge(conn, *, name: str, target_pct: float,
                     start_date: str, end_date: str, baseline_days: int = 7) -> int:
    validate_date(start_date)
    validate_date(end_date)
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    target_pct = float(target_pct)
    if not 0 < target_pct < 100:
        raise ValueError("target_pct must be between 0 and 100")
    baseline_days = int(baseline_days)
    if baseline_days < 1:
        raise ValueError("baseline_days must be >= 1")
    cur = conn.execute(
        "INSERT INTO challenges (name, target_pct, start_date, end_date,"
        " baseline_days, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, target_pct, start_date, end_date, baseline_days, utcnow()),
    )
    conn.commit()
    return cur.lastrowid


def get_challenge(conn, challenge_id: int):
    row = conn.execute(
        "SELECT * FROM challenges WHERE id = ?", (challenge_id,)).fetchone()
    if row is None:
        raise KeyError(f"no challenge with id {challenge_id}")
    return row


def list_challenges(conn):
    return conn.execute("SELECT * FROM challenges ORDER BY id").fetchall()


def join_challenge(conn, *, challenge_id: int, user: str) -> None:
    get_challenge(conn, challenge_id)  # raises KeyError when missing
    try:
        conn.execute(
            "INSERT INTO memberships (challenge_id, user, joined_at)"
            " VALUES (?, ?, ?)",
            (challenge_id, user, utcnow()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"{user!r} already joined challenge {challenge_id}")


def challenge_members(conn, challenge_id: int) -> list[str]:
    get_challenge(conn, challenge_id)  # raises KeyError when missing
    return [
        r["user"]
        for r in conn.execute(
            "SELECT user FROM memberships WHERE challenge_id = ? ORDER BY joined_at",
            (challenge_id,),
        ).fetchall()
    ]
