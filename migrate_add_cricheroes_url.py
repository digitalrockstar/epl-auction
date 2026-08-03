"""
One-off schema migration: adds the cricheroes_url column to the players
table. This app has no migration tool (no Alembic) - Base.metadata.create_all()
only creates missing tables, it never alters existing ones. Run this once
against any database that already has a players table (i.e. Neon prod, or a
local sqlite db you created before this column existed).

    python migrate_add_cricheroes_url.py

Safe to re-run - if the column's already there, it just says so and exits.
Works against both SQLite and Postgres.
"""
from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE players ADD COLUMN cricheroes_url VARCHAR"))
        conn.commit()
        print("Added cricheroes_url column to players.")
    except Exception as e:
        msg = str(e).lower()
        if "duplicate column" in msg or "already exists" in msg:
            print("cricheroes_url column already exists, nothing to do.")
        else:
            raise
