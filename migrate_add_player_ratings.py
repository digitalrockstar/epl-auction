"""
Creates player_ratings: manager-only ratings/notes per player, one row
per (team, player). Not tied to auction outcome - managers can rate
players before or during the auction for their own reference.

Run once:  python migrate_add_player_ratings.py
Safe to re-run.
"""
from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS player_ratings (
            id SERIAL PRIMARY KEY,
            team_id INTEGER NOT NULL REFERENCES teams(id),
            player_id INTEGER NOT NULL REFERENCES players(id),
            batting INTEGER,
            bowling INTEGER,
            fielding INTEGER,
            overall INTEGER,
            pool_grade TEXT,
            priority_level TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (team_id, player_id)
        )
        """
    ))
    conn.commit()
    print("player_ratings table ready.")
