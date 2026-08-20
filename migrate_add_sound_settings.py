"""
Adds sound_bid, sound_result, sound_timer, sound_roll to settings.
Run once:  python migrate_add_sound_settings.py
Safe to re-run.
"""
from sqlalchemy import text
from app.database import engine

cols = [
    ("sound_bid", "TEXT DEFAULT 'classic'"),
    ("sound_result", "TEXT DEFAULT 'classic'"),
    ("sound_timer", "TEXT DEFAULT 'tick'"),
    ("sound_roll", "TEXT DEFAULT 'whoosh'"),
]

with engine.connect() as conn:
    for name, ddl in cols:
        try:
            conn.execute(text(f"ALTER TABLE settings ADD COLUMN {name} {ddl}"))
            conn.commit()
        except Exception:
            conn.rollback()
    print("settings sound columns ready.")
