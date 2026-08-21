"""
One-off schema migration for: play/pause + team timeouts, reset-till-time
support (created_at on matches/playing_xi), and the light/dark theme
toggle. Run once against any database created before these columns
existed:

    python migrate_add_pause_timeout.py

Safe to re-run - if a column's already there, it just says so and moves
on. Works against both SQLite and Postgres.
"""
from sqlalchemy import text
from app.database import engine

STATEMENTS = [
    ("auctions", "paused_remaining_seconds", "ALTER TABLE auctions ADD COLUMN paused_remaining_seconds INTEGER"),
    ("auctions", "timeout_team_id", "ALTER TABLE auctions ADD COLUMN timeout_team_id INTEGER"),
    ("auctions", "timeout_started_at", "ALTER TABLE auctions ADD COLUMN timeout_started_at TIMESTAMP"),
    ("teams", "timeouts_used", "ALTER TABLE teams ADD COLUMN timeouts_used INTEGER DEFAULT 0"),
    ("settings", "timeout_seconds", "ALTER TABLE settings ADD COLUMN timeout_seconds INTEGER DEFAULT 30"),
    ("settings", "max_timeouts_per_team", "ALTER TABLE settings ADD COLUMN max_timeouts_per_team INTEGER DEFAULT 1"),
    ("settings", "light_theme", "ALTER TABLE settings ADD COLUMN light_theme BOOLEAN DEFAULT FALSE"),
    ("matches", "created_at", "ALTER TABLE matches ADD COLUMN created_at TIMESTAMP"),
    ("playing_xi", "created_at", "ALTER TABLE playing_xi ADD COLUMN created_at TIMESTAMP"),
]

with engine.connect() as conn:
    for table, name, ddl in STATEMENTS:
        try:
            conn.execute(text(ddl))
            if "INTEGER" in ddl and "DEFAULT 0" in ddl:
                conn.execute(text(f"UPDATE {table} SET {name} = 0 WHERE {name} IS NULL"))
            conn.commit()
            print(f"Added {name} column to {table}.")
        except Exception as e:
            conn.rollback()  # Postgres aborts the whole transaction on error - must clear it before continuing
            msg = str(e).lower()
            if "duplicate column" in msg or "already exists" in msg:
                print(f"{table}.{name} already exists, nothing to do.")
            else:
                raise

    for table in ("matches", "playing_xi"):
        try:
            conn.execute(text(f"UPDATE {table} SET created_at = '2026-01-01 00:00:00' WHERE created_at IS NULL"))
            conn.commit()
        except Exception:
            conn.rollback()
    print("Backfilled created_at on existing matches/playing_xi rows.")
