from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player, Team, Auction, AuctionType, AuctionStatus, Bid, User, Role, PlayerTeamImage
from app.auth import require_role, require_login
from app.config import TIMER_SECONDS
from app.bidding import next_bid_amount, purse_check, base_price_for
from app.notify import notify

router = APIRouter()
from app.templating import templates
staff_only = require_role(Role.super_admin, Role.admin)


from app.images import resolve_player_photo


def _player_photo(db: Session, player: Player, team_id):
    team = db.query(Team).filter(Team.id == team_id).first() if team_id else None
    return resolve_player_photo(player, team)


def _players_bought(db: Session, team_id: int) -> int:
    return db.query(Player).filter(Player.team_id == team_id).count()


def _redirect(auction_type: str, msg: str = None):
    url = f"/admin/auction?auction_type={auction_type}"
    if msg:
        url += f"&msg={msg}"
    return RedirectResponse(url=url, status_code=303)


def _finalize_expired(db: Session, auction: Auction):
    """Called opportunistically on every poll. If the timer's run out, resolve
    the auction automatically: sold to the leader, or unsold if no bids."""
    if not auction or auction.status != AuctionStatus.live:
        return
    deadline = (auction.last_action_at or auction.started_at) + timedelta(seconds=TIMER_SECONDS)
    if datetime.utcnow() < deadline:
        return

    if auction.current_team_id:
        team = db.query(Team).filter(Team.id == auction.current_team_id).first()
        auction.status = AuctionStatus.sold
        auction.closed_at = datetime.utcnow()
        player = auction.player
        player.sold_price = auction.current_bid
        if auction.auction_type == AuctionType.captain:
            player.is_captain = True
            player.team_id = team.id
            team.captain_id = player.id
        else:
            player.team_id = team.id
        team.purse_spent = (team.purse_spent or 0) + auction.current_bid
        db.commit()
        notify(f"SOLD: {player.user.name} to {team.name} for {auction.current_bid}")
    else:
        auction.status = AuctionStatus.unsold
        auction.closed_at = datetime.utcnow()
        db.commit()
        notify(f"UNSOLD: {auction.player.user.name} (timer expired, no bids)")


@router.get("/admin/auction", response_class=HTMLResponse)
def auction_console(
    request: Request,
    auction_type: str = "player",
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    _finalize_expired(db, live)
    if live and live.status != AuctionStatus.live:
        live = None

    a_type = AuctionType.captain if auction_type == "captain" else AuctionType.player
    sold_ids = [row[0] for row in db.query(Auction.player_id).filter(Auction.status == AuctionStatus.sold)]
    query = db.query(Player).join(Player.user).filter(Player.id.notin_(sold_ids))
    if a_type == AuctionType.captain:
        pool = query.filter(Player.wants_captaincy == True, Player.team_id.is_(None)).all()  # noqa: E712
    else:
        pool = query.filter(Player.team_id.is_(None)).all()

    teams = db.query(Team).order_by(Team.id).all()
    live_photo = _player_photo(db, live.player, live.current_team_id) if live else None
    min_next_bid = next_bid_amount(live) if live else None
    seconds_left = None
    if live:
        deadline = (live.last_action_at or live.started_at) + timedelta(seconds=TIMER_SECONDS)
        seconds_left = max(0, int((deadline - datetime.utcnow()).total_seconds()))
    can_undo = bool(live and live.bids)

    return templates.TemplateResponse(
        "admin/auction_console.html",
        {
            "request": request, "user": user, "live": live, "live_photo": live_photo,
            "pool": pool, "teams": teams, "auction_type": auction_type,
            "msg": msg, "min_next_bid": min_next_bid, "seconds_left": seconds_left,
            "timer_total": TIMER_SECONDS, "can_undo": can_undo,
        },
    )


@router.post("/admin/auction/start/{player_id}", response_class=HTMLResponse)
def start_auction(
    player_id: int,
    auction_type: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    if db.query(Auction).filter(Auction.status == AuctionStatus.live).first():
        return _redirect(auction_type, "Another auction is already live, close it first")

    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        return _redirect(auction_type, "Player not found")
    if player.team_id:
        return _redirect(auction_type, "Player already belongs to a team")

    a_type = AuctionType.captain if auction_type == "captain" else AuctionType.player
    base_price = base_price_for(a_type)
    now = datetime.utcnow()
    auction = Auction(
        auction_type=a_type, player_id=player_id, status=AuctionStatus.live,
        base_price=base_price, current_bid=base_price, started_at=now, last_action_at=now,
    )
    db.add(auction)
    db.commit()
    return _redirect(auction_type)


@router.post("/admin/auction/{auction_id}/bid", response_class=HTMLResponse)
def place_bid(
    auction_id: int,
    team_id: int = Form(...),
    auction_type: str = Form("player"),
    amount: int = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id, Auction.status == AuctionStatus.live).first()
    if not auction:
        return _redirect(auction_type, "This auction is no longer live")

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        return _redirect(auction_type, "Team not found")

    required = next_bid_amount(auction)
    bid_amount = amount if amount else required
    if bid_amount < required:
        return _redirect(auction_type, f"Bid must be at least {required}")

    bought = _players_bought(db, team_id)
    err = purse_check(team, auction.auction_type, bid_amount, bought)
    if err:
        return _redirect(auction_type, err)

    db.add(Bid(auction_id=auction.id, team_id=team_id, amount=bid_amount, entered_by_admin_id=user.id))
    auction.current_bid = bid_amount
    auction.current_team_id = team_id
    auction.last_action_at = datetime.utcnow()
    db.commit()
    return _redirect(auction_type)


@router.post("/admin/auction/{auction_id}/undo", response_class=HTMLResponse)
def undo_bid(
    auction_id: int,
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id, Auction.status == AuctionStatus.live).first()
    if not auction:
        return _redirect(auction_type, "Auction already closed")

    last_bid = (
        db.query(Bid).filter(Bid.auction_id == auction.id).order_by(Bid.created_at.desc()).first()
    )
    if not last_bid:
        return _redirect(auction_type, "No bids to undo")

    db.delete(last_bid)
    db.flush()
    prev = (
        db.query(Bid).filter(Bid.auction_id == auction.id).order_by(Bid.created_at.desc()).first()
    )
    if prev:
        auction.current_bid = prev.amount
        auction.current_team_id = prev.team_id
    else:
        auction.current_bid = auction.base_price
        auction.current_team_id = None
    auction.last_action_at = datetime.utcnow()
    db.commit()
    return _redirect(auction_type)


@router.post("/admin/auction/{auction_id}/sold", response_class=HTMLResponse)
def mark_sold(
    auction_id: int,
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id, Auction.status == AuctionStatus.live).first()
    if not auction:
        return _redirect(auction_type, "Auction already closed")
    if not auction.current_team_id:
        return _redirect(auction_type, "No bids placed yet, cannot mark sold")

    team = db.query(Team).filter(Team.id == auction.current_team_id).first()
    if auction.current_bid > team.purse_remaining:
        return _redirect(auction_type, "Bid exceeds team's remaining purse, cannot finalize")

    auction.status = AuctionStatus.sold
    auction.closed_at = datetime.utcnow()
    player = auction.player
    player.sold_price = auction.current_bid

    if auction.auction_type == AuctionType.captain:
        player.is_captain = True
        player.team_id = team.id
        team.captain_id = player.id
    else:
        player.team_id = team.id
    team.purse_spent = (team.purse_spent or 0) + auction.current_bid
    db.commit()
    notify(f"SOLD: {player.user.name} to {team.name} for {auction.current_bid}")
    return _redirect(auction_type)


@router.post("/admin/auction/{auction_id}/unsold", response_class=HTMLResponse)
def mark_unsold(
    auction_id: int,
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id, Auction.status == AuctionStatus.live).first()
    if not auction:
        return _redirect(auction_type, "Auction already closed")
    auction.status = AuctionStatus.unsold
    auction.closed_at = datetime.utcnow()
    db.commit()
    notify(f"UNSOLD: {auction.player.user.name}")
    return _redirect(auction_type)


def _live_context(db: Session):
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    _finalize_expired(db, live)
    if live and live.status != AuctionStatus.live:
        live = None
    photo = _player_photo(db, live.player, live.current_team_id) if live else None
    seconds_left = None
    recent_bids = []
    if live:
        deadline = (live.last_action_at or live.started_at) + timedelta(seconds=TIMER_SECONDS)
        seconds_left = max(0, int((deadline - datetime.utcnow()).total_seconds()))
        recent_bids = (
            db.query(Bid).filter(Bid.auction_id == live.id).order_by(Bid.created_at.desc()).limit(6).all()
        )
    teams = db.query(Team).order_by(Team.id).all()
    return live, photo, seconds_left, teams, recent_bids


@router.get("/auction/live", response_class=HTMLResponse)
def live_view(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    live, photo, seconds_left, teams, recent_bids = _live_context(db)
    return templates.TemplateResponse(
        "auction/live.html",
        {"request": request, "live": live, "photo": photo, "seconds_left": seconds_left,
         "timer_total": TIMER_SECONDS, "teams": teams, "recent_bids": recent_bids, "fragment_url": "/auction/live/fragment"},
    )


@router.get("/auction/live/fragment", response_class=HTMLResponse)
def live_fragment(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    live, photo, seconds_left, teams, recent_bids = _live_context(db)
    return templates.TemplateResponse(
        "auction/_live_fragment.html",
        {"request": request, "live": live, "photo": photo, "seconds_left": seconds_left,
         "timer_total": TIMER_SECONDS, "teams": teams, "recent_bids": recent_bids, "is_fragment": True},
    )
