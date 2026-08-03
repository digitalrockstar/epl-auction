from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import TIMER_SECONDS, REVEAL_SECONDS
from app.routes.auction import _live_context, _padded_photos, _eligible_pool

router = APIRouter(prefix="/spectator")
from app.templating import templates


@router.get("/live", response_class=HTMLResponse)
def spectator_live(request: Request, db: Session = Depends(get_db)):
    live, photo, seconds_left, teams, recent_bids, sold_auctions, pending, reveal_seconds_left, reveal_category = (
        _live_context(db)
    )
    reveal_photos = _padded_photos(db, _eligible_pool(db, pending.auction_type, reveal_category)) if pending else []
    return templates.TemplateResponse(
        "auction/live.html",
        {"request": request, "live": live, "photo": photo, "seconds_left": seconds_left,
         "timer_total": TIMER_SECONDS, "teams": teams, "recent_bids": recent_bids,
         "sold_auctions": sold_auctions, "fragment_url": "/spectator/live/fragment",
         "timer_fragment_url": "/spectator/live/timer", "ticker_fragment_url": "/spectator/live/ticker",
         "pending": pending, "reveal_seconds_left": reveal_seconds_left, "reveal_total": REVEAL_SECONDS,
         "reveal_category": reveal_category, "reveal_photos": reveal_photos},
    )


@router.get("/live/fragment", response_class=HTMLResponse)
def spectator_fragment(request: Request, db: Session = Depends(get_db)):
    live, photo, seconds_left, teams, recent_bids, sold_auctions, pending, reveal_seconds_left, reveal_category = (
        _live_context(db)
    )
    reveal_photos = _padded_photos(db, _eligible_pool(db, pending.auction_type, reveal_category)) if pending else []
    return templates.TemplateResponse(
        "auction/_live_fragment.html",
        {"request": request, "live": live, "photo": photo, "seconds_left": seconds_left,
         "timer_total": TIMER_SECONDS, "teams": teams, "recent_bids": recent_bids,
         "sold_auctions": sold_auctions, "pending": pending, "reveal_category": reveal_category,
         "reveal_photos": reveal_photos},
    )


@router.get("/live/timer", response_class=HTMLResponse)
def spectator_timer(request: Request, db: Session = Depends(get_db)):
    live, photo, seconds_left, teams, recent_bids, sold_auctions, pending, reveal_seconds_left, reveal_category = (
        _live_context(db)
    )
    return templates.TemplateResponse(
        "auction/_timer_fragment.html",
        {"request": request, "live": live, "seconds_left": seconds_left,
         "pending": pending, "reveal_seconds_left": reveal_seconds_left, "reveal_total": REVEAL_SECONDS},
    )


@router.get("/live/ticker", response_class=HTMLResponse)
def spectator_ticker(request: Request, db: Session = Depends(get_db)):
    live, photo, seconds_left, teams, recent_bids, sold_auctions, pending, reveal_seconds_left, reveal_category = (
        _live_context(db)
    )
    return templates.TemplateResponse(
        "auction/_ticker_fragment.html",
        {"request": request, "sold_auctions": sold_auctions},
    )
