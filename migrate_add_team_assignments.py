"""
Creates team_assignments: slot-machine reveal result binding each schedule
placeholder (Team A..D) to a real team. Standalone from auction data.

Run once:  python migrate_add_team_assignments.py
Safe to re-run.
"""
from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS team_assignments (
            id SERIAL PRIMARY KEY,
            slot_label TEXT NOT NULL UNIQUE,
            team_id INTEGER REFERENCES teams(id),
            rolled_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    ))
    conn.commit()

    for slot in ("Team A", "Team B", "Team C", "Team D"):
        try:
            conn.execute(text(
                "INSERT INTO team_assignments (slot_label) VALUES (:slot)"
            ), {"slot": slot})
            conn.commit()
        except Exception:
            conn.rollback()

    print("team_assignments table ready.")
