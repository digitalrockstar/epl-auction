import json
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import Settings
from app.config import INCREMENT_SLABS as DEFAULT_SLABS, TICKER_SPEED_SECONDS, TICKER_WINDOW, TIMER_SECONDS


def get_settings(db: Session) -> Settings:
    s = db.query(Settings).first()
    if not s:
        s = Settings(
            id=1, telegram_enabled=True, timer_seconds=TIMER_SECONDS,
            ticker_speed_seconds=TICKER_SPEED_SECONDS, ticker_window=TICKER_WINDOW,
            captain_auction_at=datetime(2026, 8, 7, 21, 0), player_auction_at=datetime(2026, 8, 22, 17, 0),
        )
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def get_slabs(db: Session):
    """Returns the increment slabs as [(ceiling, increment), ...], ceiling=inf for the
    open-ended last slab. Falls back to the config.py defaults if nothing's been saved."""
    s = get_settings(db)
    if not s.increment_slabs:
        return DEFAULT_SLABS
    try:
        raw = json.loads(s.increment_slabs)
        return [(float(c) if c is not None else float("inf"), int(i)) for c, i in raw]
    except (ValueError, TypeError):
        return DEFAULT_SLABS


def slabs_to_json(slabs) -> str:
    return json.dumps([[None if c == float("inf") else c, i] for c, i in slabs])
