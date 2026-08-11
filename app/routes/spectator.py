from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import REVEAL_SECONDS
from app.models import Auction, AuctionStatus
from app.routes.auction import _live_context, _padded_photos, _eligible_pool, _next_auction_countdown

router = APIRouter(prefix="/spectator")
from app.templating import templates


@router.get("/live", response_class=HTMLResponse)
def spectator_live(request: Request, db: Session = Depends(get_db)):
    ctx = _live_context(db)
    pending = ctx["pending"]
    reveal_photos = _padded_photos(db, _eligible_pool(db, pending.auction_type, ctx["reveal_category"])) if pending else []
    screen_state, countdown_target = _next_auction_countdown(db)
    show_countdown = screen_state is not None and not (ctx["live"] or pending)
    return templates.TemplateResponse(
        "auction/live.html",
        {"request": request, "live": ctx["live"], "photo": ctx["photo"], "seconds_left": ctx["seconds_left"],
         "timer_total": ctx["timer_seconds"], "teams": ctx["teams"], "recent_bids": ctx["recent_bids"],
         "sold_auctions": ctx["sold_auctions"], "fragment_url": "/spectator/live/fragment",
         "timer_fragment_url": "/spectator/live/timer", "ticker_fragment_url": "/spectator/live/ticker",
         "countdown_fragment_url": "/spectator/live/countdown",
         "pending": pending, "reveal_seconds_left": ctx["reveal_seconds_left"], "reveal_total": REVEAL_SECONDS,
         "reveal_category": ctx["reveal_category"], "reveal_photos": reveal_photos, "ticker_speed": ctx["ticker_speed"],
         "resolved": ctx["resolved"], "resolved_photo": ctx["resolved_photo"],
         "is_paused": ctx["is_paused"], "timeout_team": ctx["timeout_team"], "timeout_seconds_left": ctx["timeout_seconds_left"],
         "screen_state": screen_state, "countdown_target": countdown_target, "show_countdown": show_countdown},
    )


@router.get("/live/fragment", response_class=HTMLResponse)
def spectator_fragment(request: Request, db: Session = Depends(get_db)):
    ctx = _live_context(db)
    pending = ctx["pending"]
    reveal_photos = _padded_photos(db, _eligible_pool(db, pending.auction_type, ctx["reveal_category"])) if pending else []
    return templates.TemplateResponse(
        "auction/_live_fragment.html",
        {"request": request, "live": ctx["live"], "photo": ctx["photo"], "seconds_left": ctx["seconds_left"],
         "timer_total": ctx["timer_seconds"], "teams": ctx["teams"], "recent_bids": ctx["recent_bids"],
         "sold_auctions": ctx["sold_auctions"], "pending": pending, "reveal_category": ctx["reveal_category"],
         "reveal_photos": reveal_photos, "resolved": ctx["resolved"], "resolved_photo": ctx["resolved_photo"],
         "is_paused": ctx["is_paused"], "timeout_team": ctx["timeout_team"], "timeout_seconds_left": ctx["timeout_seconds_left"]},
    )


@router.get("/live/timer", response_class=HTMLResponse)
def spectator_timer(request: Request, db: Session = Depends(get_db)):
    ctx = _live_context(db)
    return templates.TemplateResponse(
        "auction/_timer_fragment.html",
        {"request": request, "live": ctx["live"], "seconds_left": ctx["seconds_left"],
         "pending": ctx["pending"], "reveal_seconds_left": ctx["reveal_seconds_left"], "reveal_total": REVEAL_SECONDS,
         "is_paused": ctx["is_paused"], "timeout_team": ctx["timeout_team"], "timeout_seconds_left": ctx["timeout_seconds_left"]},
    )


@router.get("/live/countdown", response_class=HTMLResponse)
def spectator_countdown(request: Request, db: Session = Depends(get_db)):
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    pending = db.query(Auction).filter(Auction.status == AuctionStatus.pending).first()
    screen_state, countdown_target = _next_auction_countdown(db)
    if live or pending:
        screen_state = "live"
    return templates.TemplateResponse(
        "auction/_countdown_fragment.html",
        {"request": request, "screen_state": screen_state, "countdown_target": countdown_target},
    )


@router.get("/live/ticker", response_class=HTMLResponse)
def spectator_ticker(request: Request, db: Session = Depends(get_db)):
    ctx = _live_context(db)
    return templates.TemplateResponse(
        "auction/_ticker_fragment.html",
        {"request": request, "sold_auctions": ctx["sold_auctions"], "ticker_speed": ctx["ticker_speed"]},
    )
