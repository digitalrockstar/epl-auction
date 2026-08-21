"""
Adds the `theme` column to render_bandwidth (used by push_theme_env.py,
was previously applied ad hoc / undocumented in this repo).
Run once:  python migrate_add_render_bandwidth_theme.py
Safe to re-run.
"""
from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE render_bandwidth ADD COLUMN theme TEXT"))
        conn.commit()
    except Exception:
        conn.rollback()
    print("render_bandwidth.theme ready.")
