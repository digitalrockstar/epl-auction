import random
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Auction, AuctionType, AuctionStatus, User, Role
from app.auth import require_role
from app.config import REVEAL_SECONDS, SKILL_CATEGORIES
from app.bidding import base_price_for
from app.routes.auction import _current_auction, _eligible_pool, _player_photo

router = APIRouter(prefix="/admin/roll")
from app.templating import templates
staff_only = require_role(Role.super_admin, Role.admin)


def _category_counts(db: Session, a_type: AuctionType):
    return {c: len(_eligible_pool(db, a_type, c)) for c in SKILL_CATEGORIES}


@router.get("", response_class=HTMLResponse)
def roll_page(
    request: Request,
    auction_type: str = "player",
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    a_type = AuctionType.captain if auction_type == "captain" else AuctionType.player
    live, pending = _current_auction(db)
    counts = _category_counts(db, a_type)
    return templates.TemplateResponse(
        "admin/roll.html",
        {"request": request, "user": user, "auction_type": auction_type, "msg": msg,
         "categories": SKILL_CATEGORIES, "counts": counts, "live": live, "pending": pending},
    )


@router.post("/spin", response_class=HTMLResponse)
def spin(
    auction_type: str = Form(...),
    category: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    def back(msg: str = None):
        url = f"/admin/roll?auction_type={auction_type}"
        if msg:
            url += f"&msg={msg}"
        return RedirectResponse(url=url, status_code=303)

    if category not in SKILL_CATEGORIES:
        return back("Unknown category")

    live, pending = _current_auction(db)
    if live or pending:
        return back("An auction is already live or revealing, finish that first")

    a_type = AuctionType.captain if auction_type == "captain" else AuctionType.player
    pool = _eligible_pool(db, a_type, category)
    if not pool:
        return back(f"{category} pool is done - move to the next category")

    chosen = random.choice(pool)
    base_price = base_price_for(a_type)
    now = datetime.utcnow()
    auction = Auction(
        auction_type=a_type, player_id=chosen.id, status=AuctionStatus.pending,
        base_price=base_price, current_bid=base_price, started_at=now,
    )
    db.add(auction)
    db.commit()
    return RedirectResponse(url=f"/admin/roll/reveal?auction_type={auction_type}", status_code=303)


@router.get("/reveal", response_class=HTMLResponse)
def reveal_page(
    request: Request,
    auction_type: str = "player",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    live, pending = _current_auction(db)
    if live:
        return RedirectResponse(url=f"/admin/auction?auction_type={auction_type}", status_code=303)
    if not pending:
        return RedirectResponse(url=f"/admin/roll?auction_type={auction_type}", status_code=303)

    photo = _player_photo(db, pending.player, None)
    reveal_seconds_left = max(0, REVEAL_SECONDS - int((datetime.utcnow() - pending.started_at).total_seconds()))

    return templates.TemplateResponse(
        "admin/roll_reveal.html",
        {"request": request, "user": user, "auction_type": auction_type, "pending": pending,
         "photo": photo, "reveal_seconds_left": reveal_seconds_left, "reveal_total": REVEAL_SECONDS},
    )


@router.get("/status", response_class=HTMLResponse)
def reveal_status(
    request: Request,
    auction_type: str = "player",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    """Polled by the reveal page for the countdown; also promotes pending -> live
    when the reveal window elapses, so the page can redirect on its own."""
    live, pending = _current_auction(db)
    reveal_seconds_left = None
    if pending:
        reveal_seconds_left = max(0, REVEAL_SECONDS - int((datetime.utcnow() - pending.started_at).total_seconds()))
    return templates.TemplateResponse(
        "admin/_roll_status_fragment.html",
        {"request": request, "auction_type": auction_type, "live": live, "pending": pending,
         "reveal_seconds_left": reveal_seconds_left},
    )
