"""
One-off schema migration: adds captain_auction_at / player_auction_at columns
to the settings table (for the TV/spectator countdown timers). Run once
against any database created before these columns existed:

    python migrate_add_auction_countdowns.py

Safe to re-run - if a column's already there, it just says so and exits.
Works against both SQLite and Postgres.
"""
from sqlalchemy import text
from app.database import engine

COLUMNS = [
    ("captain_auction_at", "TIMESTAMP", "2026-08-07 21:00:00"),
    ("player_auction_at", "TIMESTAMP", "2026-08-22 17:00:00"),
]

with engine.connect() as conn:
    for name, col_type, default in COLUMNS:
        try:
            conn.execute(text(f"ALTER TABLE settings ADD COLUMN {name} {col_type}"))
            conn.execute(text(f"UPDATE settings SET {name} = '{default}' WHERE {name} IS NULL"))
            conn.commit()
            print(f"Added {name} column to settings.")
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column" in msg or "already exists" in msg:
                print(f"{name} column already exists, nothing to do.")
            else:
                raise
