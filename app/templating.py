from fastapi.templating import Jinja2Templates
from app.images import resolve_player_photo, resolve_team_logo


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
templates.env.filters["inr"] = inr
