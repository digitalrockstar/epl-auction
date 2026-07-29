from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import TIMER_SECONDS
from app.routes.auction import _live_context

router = APIRouter(prefix="/spectator")
templates = Jinja2Templates(directory="app/templates")


@router.get("/live", response_class=HTMLResponse)
def spectator_live(request: Request, db: Session = Depends(get_db)):
    live, photo, seconds_left, teams = _live_context(db)
    return templates.TemplateResponse(
        "auction/live.html",
        {"request": request, "live": live, "photo": photo, "seconds_left": seconds_left,
         "timer_total": TIMER_SECONDS, "teams": teams, "fragment_url": "/spectator/live/fragment"},
    )


@router.get("/live/fragment", response_class=HTMLResponse)
def spectator_fragment(request: Request, db: Session = Depends(get_db)):
    live, photo, seconds_left, teams = _live_context(db)
    return templates.TemplateResponse(
        "auction/_live_fragment.html",
        {"request": request, "live": live, "photo": photo, "seconds_left": seconds_left,
         "timer_total": TIMER_SECONDS, "teams": teams},
    )
