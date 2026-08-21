"""
One-off schema migration: creates the `render_bandwidth` table used to
track monthly bandwidth per Render free-tier account, so the login page
can redirect spectators to whichever hosted URL has the most headroom.

Run once:

    python migrate_add_render_bandwidth.py

Safe to re-run. Works against both SQLite and Postgres.
"""
from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS render_bandwidth (
            account TEXT PRIMARY KEY,
            service_url TEXT NOT NULL,
            usage_gb NUMERIC NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    ))
    conn.commit()
    print("render_bandwidth table ready.")
