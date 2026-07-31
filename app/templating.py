from fastapi.templating import Jinja2Templates
from app.images import resolve_player_photo, resolve_team_logo

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["player_photo"] = resolve_player_photo
templates.env.globals["team_logo"] = resolve_team_logo
