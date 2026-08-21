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
            max_budget INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (team_id, player_id)
        )
        """
    ))
    try:
        conn.execute(text("ALTER TABLE player_ratings ADD COLUMN IF NOT EXISTS max_budget INTEGER"))
        conn.commit()
    except Exception:
        conn.rollback()
    print("player_ratings table ready (max_budget).")
