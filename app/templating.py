from fastapi.templating import Jinja2Templates
from app.images import resolve_player_photo, resolve_team_logo
import os


def static_version(rel_path: str) -> str:
    """Mtime of a static file, appended as a cache-busting query string so
    browsers refetch CSS/JS after a deploy instead of serving a stale cache."""
    full_path = os.path.join(os.path.dirname(__file__), "static", rel_path)
    try:
        return str(int(os.path.getmtime(full_path)))
    except OSError:
        return "0"


def theme_attr() -> str:
    """Reads the light/dark toggle straight from Settings, independent of
    whatever context each route happens to pass in - every page needs this,
    including ones that never touch Settings otherwise."""
    from app.database import SessionLocal
    from app.models import Settings
    db = SessionLocal()
    try:
        s = db.query(Settings).first()
        return "light" if (s and s.light_theme) else "dark"
    finally:
        db.close()


def inr(value):
    """Format a number in Indian digit grouping: ##,##,###."""
    if value is None:
        return "-"
    n = int(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    s = str(n)
    if len(s) <= 3:
        return sign + s
    last3 = s[-3:]
    rest = s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return sign + ",".join(parts) + "," + last3


templates = Jinja2Templates(directory="app/templates")
templates.env.globals["player_photo"] = resolve_player_photo
templates.env.globals["team_logo"] = resolve_team_logo
templates.env.globals["static_version"] = static_version
templates.env.globals["theme_attr"] = theme_attr
templates.env.filters["inr"] = inr
