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


VALID_THEMES = {"dark", "light", "epl-night", "graphite-gold", "pinky-green", "ember-teal", "carbon-lime", "cobalt-flame", "desert-electric", "midnight-coral", "arctic-mango", "plum-copper", "mono-acid", "tang-cobalt", "uv-mint", "royal-circuit", "warm-ivory", "clean-broadcast"}


def theme_attr() -> str:
    """Reads the active theme straight from Settings, independent of
    whatever context each route happens to pass in - every page needs this,
    including ones that never touch Settings otherwise."""
    from app.database import SessionLocal
    from app.models import Settings
    db = SessionLocal()
    try:
        s = db.query(Settings).first()
        if s and s.theme in VALID_THEMES:
            return s.theme
        if s and s.light_theme:  # fall back for rows saved before the theme column existed
            return "light"
        return "dark"
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
