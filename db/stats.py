import sqlite3
import json
from datetime import datetime, date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "runclub.db"


def _conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                username TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                weight_kg REAL DEFAULT 65,
                pace_min_per_km REAL DEFAULT 7,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                date TEXT NOT NULL,
                total_km REAL NOT NULL,
                calories REAL NOT NULL,
                minutes INTEGER NOT NULL,
                route_json TEXT,
                FOREIGN KEY (username) REFERENCES profiles(username)
            );
            CREATE TABLE IF NOT EXISTS training_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                goal TEXT NOT NULL,
                weeks INTEGER NOT NULL,
                current_km REAL NOT NULL,
                plan_json TEXT NOT NULL,
                start_date TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES profiles(username)
            );
            CREATE TABLE IF NOT EXISTS meetups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator TEXT NOT NULL,
                title TEXT NOT NULL,
                meetup_date TEXT NOT NULL,
                meetup_time TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                route_km REAL,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS saved_routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                total_km REAL NOT NULL,
                geometry_json TEXT NOT NULL,
                waypoints_json TEXT NOT NULL,
                agent_summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES profiles(username)
            );
        """)


# ── Profile ─────────────────────────────────────────────────────

def save_profile(username: str, display_name: str, weight_kg: float, pace: float):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO profiles (username, display_name, weight_kg, pace_min_per_km)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                display_name=excluded.display_name,
                weight_kg=excluded.weight_kg,
                pace_min_per_km=excluded.pace_min_per_km
        """, (username, display_name, weight_kg, pace))


def get_profile(username: str):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None


# ── Runs ─────────────────────────────────────────────────────────

def save_run(username: str, total_km: float, calories: float, minutes: int, route_data: dict):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO runs (username, date, total_km, calories, minutes, route_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, datetime.now().strftime("%Y-%m-%d %H:%M"), total_km, calories, minutes, json.dumps(route_data)))


def get_runs(username: str) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE username=? ORDER BY date DESC LIMIT 20", (username,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats(username: str) -> dict:
    with _conn() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as total_runs,
                   COALESCE(SUM(total_km), 0) as total_km,
                   COALESCE(SUM(calories), 0) as total_calories,
                   COALESCE(AVG(total_km), 0) as avg_km
            FROM runs WHERE username=?
        """, (username,)).fetchone()
        return dict(row) if row else {}


# ── Streak ───────────────────────────────────────────────────────

def get_streak(username: str) -> dict:
    """Calculate current streak and longest streak from run history."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT substr(date, 1, 10) as run_date FROM runs WHERE username=? ORDER BY run_date DESC",
            (username,)
        ).fetchall()

    if not rows:
        return {"current": 0, "longest": 0, "ran_today": False}

    run_dates = [date.fromisoformat(r["run_date"]) for r in rows]
    today = date.today()
    ran_today = run_dates[0] == today

    # Current streak — count backwards from today or yesterday
    current = 0
    check = today if ran_today else today - timedelta(days=1)
    for d in run_dates:
        if d == check:
            current += 1
            check -= timedelta(days=1)
        elif d < check:
            break

    # Longest streak
    longest = max(current, 1)
    tmp = 1
    for i in range(1, len(run_dates)):
        if (run_dates[i - 1] - run_dates[i]).days == 1:
            tmp += 1
            longest = max(longest, tmp)
        else:
            tmp = 1

    return {"current": current, "longest": longest, "ran_today": ran_today}


# ── Leaderboard ──────────────────────────────────────────────────

def get_weekly_leaderboard() -> list:
    """Return all users ranked by km this week (Mon–Sun)."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    with _conn() as conn:
        rows = conn.execute("""
            SELECT p.username, p.display_name,
                   COALESCE(SUM(r.total_km), 0) as week_km,
                   COALESCE(COUNT(r.id), 0) as week_runs
            FROM profiles p
            LEFT JOIN runs r
                ON p.username = r.username
                AND substr(r.date, 1, 10) >= ?
            GROUP BY p.username
            ORDER BY week_km DESC
        """, (week_start.isoformat(),)).fetchall()
    return [dict(r) for r in rows]


def get_alltime_leaderboard() -> list:
    """Return all users ranked by total km all-time."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT p.username, p.display_name,
                   COALESCE(SUM(r.total_km), 0) as total_km,
                   COALESCE(COUNT(r.id), 0) as total_runs
            FROM profiles p
            LEFT JOIN runs r ON p.username = r.username
            GROUP BY p.username
            ORDER BY total_km DESC
        """).fetchall()
    return [dict(r) for r in rows]


# ── Saved Routes ─────────────────────────────────────────────────

def save_route(username: str, name: str, lat: float, lon: float,
               total_km: float, geometry_json: str, waypoints_json: str, agent_summary: str):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO saved_routes (username, name, lat, lon, total_km, geometry_json, waypoints_json, agent_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, name, lat, lon, total_km, geometry_json, waypoints_json, agent_summary))


def get_saved_routes(username: str) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_routes WHERE username=? ORDER BY created_at DESC",
            (username,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_saved_route(route_id: int, username: str):
    with _conn() as conn:
        conn.execute("DELETE FROM saved_routes WHERE id=? AND username=?", (route_id, username))


# ── Training Plans ────────────────────────────────────────────────

def save_training_plan(username: str, goal: str, weeks: int, current_km: float,
                       plan_json: str, start_date: str):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO training_plans (username, goal, weeks, current_km, plan_json, start_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, goal, weeks, current_km, plan_json, start_date))


def get_latest_training_plan(username: str):
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM training_plans WHERE username=? ORDER BY created_at DESC LIMIT 1",
            (username,)
        ).fetchone()
    return dict(row) if row else None


# ── Meetups ───────────────────────────────────────────────────────

def save_meetup(creator: str, title: str, meetup_date: str, meetup_time: str,
                lat: float, lon: float, route_km: float, description: str):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO meetups (creator, title, meetup_date, meetup_time, lat, lon, route_km, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (creator, title, meetup_date, meetup_time, lat, lon, route_km, description))


def get_upcoming_meetups() -> list:
    today = date.today().isoformat()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT * FROM meetups WHERE meetup_date >= ? ORDER BY meetup_date, meetup_time LIMIT 20
        """, (today,)).fetchall()
    return [dict(r) for r in rows]
