"""
One-off schema migration: adds the `theme` column to settings, replacing
the old on/off light_theme checkbox with 6 named theme options. Run once:

    python migrate_add_theme_column.py

Safe to re-run. Works against both SQLite and Postgres.
"""
from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE settings ADD COLUMN theme VARCHAR DEFAULT 'dark'"))
        conn.commit()
        print("Added theme column to settings.")
    except Exception as e:
        conn.rollback()
        msg = str(e).lower()
        if "duplicate column" in msg or "already exists" in msg:
            print("settings.theme already exists, nothing to do.")
        else:
            raise

    try:
        conn.execute(text(
            "UPDATE settings SET theme = 'light' WHERE light_theme = TRUE AND (theme IS NULL OR theme = 'dark')"
        ))
        conn.commit()
        print("Backfilled theme from light_theme where needed.")
    except Exception as e:
        conn.rollback()
        print(f"Backfill skipped: {e}")
