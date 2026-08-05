from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player, Team, Auction, AuctionType, AuctionStatus, Bid, User, Role, PlayerTeamImage
from app.auth import require_role, require_login
from app.config import REVEAL_SECONDS, RESULT_HOLD_SECONDS
from app.bidding import next_bid_amount, purse_check, base_price_for
from app.app_settings import get_settings, get_slabs
from app.notify import notify, notify_sold

router = APIRouter()
from app.templating import templates
staff_only = require_role(Role.super_admin, Role.admin)


from app.images import resolve_player_photo


def _player_photo(db: Session, player: Player, team_id):
    team = db.query(Team).filter(Team.id == team_id).first() if team_id else None
    return resolve_player_photo(player, team)


def _players_bought(db: Session, team_id: int) -> int:
    return db.query(Player).filter(Player.team_id == team_id).count()


def _eligible_pool(db: Session, a_type: AuctionType, category: str = None):
    """Unsold players eligible for this auction type. Player auctions are
    scoped to a fixed skill category; captain auctions pull from every
    captain nominee regardless of skill."""
    q = db.query(Player).join(Player.user).filter(Player.team_id.is_(None))
    if a_type == AuctionType.captain:
        q = q.filter(Player.wants_captaincy.is_(True))
    else:
        q = q.filter(Player.primary_skill == category)
    return q.all()


def _padded_photos(db: Session, players, minimum: int = 6):
    """Pads a short candidate list by repeating it, so the reveal shuffle
    always has enough frames to look like a proper spin."""
    photos = [_player_photo(db, p, None) for p in players]
    if not photos:
        return []
    out = list(photos)
    i = 0
    while len(out) < minimum:
        out.append(photos[i % len(photos)])
        i += 1
    return out


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
    deadline = (auction.last_action_at or auction.started_at) + timedelta(seconds=get_settings(db).timer_seconds)
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
        if get_settings(db).telegram_enabled:
            notify_sold(player.user.name, team.name, auction.current_bid)
    else:
        auction.status = AuctionStatus.unsold
        auction.closed_at = datetime.utcnow()
        db.commit()
        if get_settings(db).telegram_enabled:
            notify(f"UNSOLD: {auction.player.user.name} (timer expired, no bids)")


def _promote_pending(db: Session, auction: Auction):
    """A 'pending' auction is a Roll reveal in progress. Once the reveal
    countdown has elapsed, flip it to live and start the real bidding
    timer fresh from this moment."""
    if not auction or auction.status != AuctionStatus.pending:
        return
    deadline = auction.started_at + timedelta(seconds=REVEAL_SECONDS)
    if datetime.utcnow() < deadline:
        return
    now = datetime.utcnow()
    auction.status = AuctionStatus.live
    auction.started_at = now
    auction.last_action_at = now
    db.commit()


def _current_auction(db: Session):
    """Resolves the single in-flight auction, if any: (live, pending).
    Only one of the two will ever be set at a time."""
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    _finalize_expired(db, live)
    if live and live.status != AuctionStatus.live:
        live = None
    pending = None
    if not live:
        pending = db.query(Auction).filter(Auction.status == AuctionStatus.pending).first()
        _promote_pending(db, pending)
        if pending and pending.status == AuctionStatus.live:
            live = pending
            pending = None
    return live, pending


@router.get("/admin/auction", response_class=HTMLResponse)
def auction_console(
    request: Request,
    auction_type: str = "player",
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    live, pending = _current_auction(db)

    a_type = AuctionType.captain if auction_type == "captain" else AuctionType.player
    sold_ids = [row[0] for row in db.query(Auction.player_id).filter(Auction.status == AuctionStatus.sold)]
    query = db.query(Player).join(Player.user).filter(Player.id.notin_(sold_ids))
    if a_type == AuctionType.captain:
        pool = query.filter(Player.wants_captaincy == True, Player.team_id.is_(None)).all()  # noqa: E712
    else:
        pool = query.filter(Player.team_id.is_(None)).all()

    teams = db.query(Team).order_by(Team.id).all()
    live_photo = _player_photo(db, live.player, live.current_team_id) if live else None
    min_next_bid = next_bid_amount(live, get_slabs(db)) if live else None
    timer_seconds = get_settings(db).timer_seconds
    seconds_left = None
    if live:
        deadline = (live.last_action_at or live.started_at) + timedelta(seconds=timer_seconds)
        seconds_left = max(0, int((deadline - datetime.utcnow()).total_seconds()))
    can_undo = bool(live and live.bids)

    return templates.TemplateResponse(
        "admin/auction_console.html",
        {
            "request": request, "user": user, "live": live, "live_photo": live_photo,
            "pool": pool, "teams": teams, "auction_type": auction_type,
            "msg": msg, "min_next_bid": min_next_bid, "seconds_left": seconds_left,
            "timer_total": timer_seconds, "can_undo": can_undo, "pending": pending,
        },
    )


@router.post("/admin/auction/start/{player_id}", response_class=HTMLResponse)
def start_auction(
    player_id: int,
    auction_type: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    if db.query(Auction).filter(Auction.status.in_([AuctionStatus.live, AuctionStatus.pending])).first():
        return _redirect(auction_type, "Another auction is already live or revealing, finish that first")

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


@router.get("/admin/auction/timer", response_class=HTMLResponse)
def admin_timer(
    request: Request,
    auction_type: str = "player",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    _finalize_expired(db, live)
    if live and live.status != AuctionStatus.live:
        live = None
    timer_seconds = get_settings(db).timer_seconds
    seconds_left = None
    if live:
        deadline = (live.last_action_at or live.started_at) + timedelta(seconds=timer_seconds)
        seconds_left = max(0, int((deadline - datetime.utcnow()).total_seconds()))
    return templates.TemplateResponse(
        "admin/_timer_fragment.html",
        {"request": request, "live": live, "seconds_left": seconds_left, "timer_total": timer_seconds},
    )


@router.get("/admin/auction/state", response_class=HTMLResponse)
def admin_state(
    request: Request,
    auction_type: str = "player",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    _finalize_expired(db, live)
    if live and live.status != AuctionStatus.live:
        live = None
    teams = db.query(Team).order_by(Team.id).all()
    min_next_bid = next_bid_amount(live, get_slabs(db)) if live else None
    can_undo = bool(live and live.bids)
    return templates.TemplateResponse(
        "admin/_live_state_fragment.html",
        {"request": request, "live": live, "teams": teams, "auction_type": auction_type,
         "min_next_bid": min_next_bid, "can_undo": can_undo},
    )


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

    required = next_bid_amount(auction, get_slabs(db))
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
    if get_settings(db).telegram_enabled:
        notify_sold(player.user.name, team.name, auction.current_bid)
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
    if get_settings(db).telegram_enabled:
        notify(f"UNSOLD: {auction.player.user.name}")
    return _redirect(auction_type)


def _live_context(db: Session):
    live, pending = _current_auction(db)
    settings = get_settings(db)
    photo = _player_photo(db, live.player, live.current_team_id) if live else None
    seconds_left = None
    recent_bids = []
    if live:
        deadline = (live.last_action_at or live.started_at) + timedelta(seconds=settings.timer_seconds)
        seconds_left = max(0, int((deadline - datetime.utcnow()).total_seconds()))
        recent_bids = (
            db.query(Bid).filter(Bid.auction_id == live.id).order_by(Bid.created_at.desc()).limit(6).all()
        )
    teams = db.query(Team).order_by(Team.id).all()
    sold_auctions = (
        db.query(Auction).filter(Auction.status == AuctionStatus.sold)
        .order_by(Auction.closed_at.asc()).all()
    )[-settings.ticker_window:]
    reveal_seconds_left = None
    reveal_category = None
    if pending:
        reveal_seconds_left = max(0, REVEAL_SECONDS - int((datetime.utcnow() - pending.started_at).total_seconds()))
        if pending.auction_type != AuctionType.captain:
            reveal_category = pending.player.primary_skill

    # Hold the most recently closed auction on screen for a few seconds
    # (SOLD / WILL BE BACK stamp) instead of letting the card vanish the
    # instant the next poll sees status flip away from "live".
    resolved = None
    resolved_photo = None
    if not live:
        last_closed = (
            db.query(Auction)
            .filter(Auction.status.in_([AuctionStatus.sold, AuctionStatus.unsold]))
            .order_by(Auction.closed_at.desc())
            .first()
        )
        if last_closed and last_closed.closed_at and \
                (datetime.utcnow() - last_closed.closed_at).total_seconds() < RESULT_HOLD_SECONDS:
            resolved = last_closed
            resolved_photo = _player_photo(db, resolved.player, resolved.current_team_id)

    return (live, photo, seconds_left, teams, recent_bids, sold_auctions, pending, reveal_seconds_left,
            reveal_category, settings.ticker_speed_seconds, settings.timer_seconds, resolved, resolved_photo)


def _next_auction_countdown(db: Session):
    """Idle-screen flip countdown: which auction's start time to show. Captain's
    auction until any captain-type auction has been rolled, then player's auction
    until any player-type auction has been rolled, then nothing."""
    settings = get_settings(db)
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    if settings.captain_auction_at and now < settings.captain_auction_at:
        return "CAPTAIN'S AUCTION", settings.captain_auction_at
    if settings.player_auction_at and now < settings.player_auction_at:
        return "PLAYER'S AUCTION", settings.player_auction_at
    return None, None


@router.get("/auction/live", response_class=HTMLResponse)
def live_view(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    (live, photo, seconds_left, teams, recent_bids, sold_auctions, pending, reveal_seconds_left,
     reveal_category, ticker_speed, timer_seconds, resolved, resolved_photo) = _live_context(db)
    reveal_photos = _padded_photos(db, _eligible_pool(db, pending.auction_type, reveal_category)) if pending else []
    countdown_label, countdown_target = _next_auction_countdown(db)
    show_countdown = countdown_target is not None
    return templates.TemplateResponse(
        "auction/live.html",
        {"request": request, "live": live, "photo": photo, "seconds_left": seconds_left,
         "timer_total": timer_seconds, "teams": teams, "recent_bids": recent_bids,
         "sold_auctions": sold_auctions, "fragment_url": "/auction/live/fragment",
         "timer_fragment_url": "/auction/live/timer", "ticker_fragment_url": "/auction/live/ticker",
         "countdown_fragment_url": "/auction/live/countdown",
         "pending": pending, "reveal_seconds_left": reveal_seconds_left, "reveal_total": REVEAL_SECONDS,
         "reveal_category": reveal_category, "reveal_photos": reveal_photos, "ticker_speed": ticker_speed,
         "resolved": resolved, "resolved_photo": resolved_photo,
         "countdown_label": countdown_label, "countdown_target": countdown_target, "show_countdown": show_countdown},
    )


@router.get("/auction/live/fragment", response_class=HTMLResponse)
def live_fragment(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    (live, photo, seconds_left, teams, recent_bids, sold_auctions, pending, reveal_seconds_left,
     reveal_category, ticker_speed, timer_seconds, resolved, resolved_photo) = _live_context(db)
    reveal_photos = _padded_photos(db, _eligible_pool(db, pending.auction_type, reveal_category)) if pending else []
    return templates.TemplateResponse(
        "auction/_live_fragment.html",
        {"request": request, "live": live, "photo": photo, "seconds_left": seconds_left,
         "timer_total": timer_seconds, "teams": teams, "recent_bids": recent_bids,
         "sold_auctions": sold_auctions, "pending": pending, "reveal_category": reveal_category,
         "reveal_photos": reveal_photos, "resolved": resolved, "resolved_photo": resolved_photo},
    )


@router.get("/auction/live/timer", response_class=HTMLResponse)
def live_timer(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    (live, photo, seconds_left, teams, recent_bids, sold_auctions, pending, reveal_seconds_left,
     reveal_category, ticker_speed, timer_seconds, resolved, resolved_photo) = _live_context(db)
    return templates.TemplateResponse(
        "auction/_timer_fragment.html",
        {"request": request, "live": live, "seconds_left": seconds_left,
         "pending": pending, "reveal_seconds_left": reveal_seconds_left, "reveal_total": REVEAL_SECONDS},
    )


@router.get("/auction/live/countdown", response_class=HTMLResponse)
def live_countdown(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    countdown_label, countdown_target = _next_auction_countdown(db)
    show_countdown = countdown_target is not None
    ctx = {"request": request, "countdown_label": countdown_label, "countdown_target": countdown_target, "show_countdown": show_countdown}
    if show_countdown:
        return templates.TemplateResponse("auction/_countdown_fragment.html", ctx)
    return templates.TemplateResponse("auction/_live_fragment.html", ctx)


@router.get("/auction/live/ticker", response_class=HTMLResponse)
def live_ticker(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    (live, photo, seconds_left, teams, recent_bids, sold_auctions, pending, reveal_seconds_left,
     reveal_category, ticker_speed, timer_seconds, resolved, resolved_photo) = _live_context(db)
    return templates.TemplateResponse(
        "auction/_ticker_fragment.html",
        {"request": request, "sold_auctions": sold_auctions, "ticker_speed": ticker_speed},
    )
