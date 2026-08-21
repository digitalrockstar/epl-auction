"""
One-off schema migration: adds ground + per-innings result columns to
matches (for auto NRR calc), drops the old ground_fee column. Run once:

    python migrate_add_match_results.py

Safe to re-run. Works against both SQLite and Postgres.
"""
from sqlalchemy import text
from app.database import engine

ADD_COLUMNS = [
    ("ground", "VARCHAR"),
    ("team_a_runs", "INTEGER"),
    ("team_a_overs", "FLOAT"),
    ("team_a_wickets", "INTEGER"),
    ("team_b_runs", "INTEGER"),
    ("team_b_overs", "FLOAT"),
    ("team_b_wickets", "INTEGER"),
]

with engine.connect() as conn:
    for col, coltype in ADD_COLUMNS:
        try:
            conn.execute(text(f"ALTER TABLE matches ADD COLUMN {col} {coltype}"))
            conn.commit()
            print(f"Added matches.{col}.")
        except Exception as e:
            conn.rollback()
            msg = str(e).lower()
            if "duplicate column" in msg or "already exists" in msg:
                print(f"matches.{col} already exists, nothing to do.")
            else:
                raise

    try:
        conn.execute(text("ALTER TABLE matches DROP COLUMN ground_fee"))
        conn.commit()
        print("Dropped matches.ground_fee.")
    except Exception as e:
        conn.rollback()
        msg = str(e).lower()
        if "does not exist" in msg or "no such column" in msg or "can't drop" in msg:
            print("matches.ground_fee already absent, nothing to do.")
        else:
            raise
