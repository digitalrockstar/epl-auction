from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player, Team, Auction, AuctionType, AuctionStatus, Bid, User, Role, PlayerTeamImage
from app.auth import require_role
from app.config import REVEAL_SECONDS, RESULT_HOLD_SECONDS, SKILL_CATEGORIES
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


def _eligible_pool(db: Session, a_type: AuctionType, category: str = None, respect_round: bool = True):
    """Unsold players eligible for this auction type. Player auctions are
    scoped to a fixed skill category; captain auctions pull from every
    captain nominee regardless of skill.

    respect_round=True (the default, used by Roll) excludes players who've
    already gone unsold in this pool/category, so the same player can't come
    up twice in a row. Once every remaining player in the pool has gone
    unsold, the exclusion lifts on its own (round 2) and they're fair game
    again."""
    q = db.query(Player).join(Player.user).filter(Player.team_id.is_(None))
    if a_type == AuctionType.captain:
        q = q.filter(Player.wants_captaincy.is_(True))
    else:
        q = q.filter(Player.primary_skill == category)
    all_pool = q.all()
    if not respect_round or not all_pool:
        return all_pool

    pool_ids = [p.id for p in all_pool]
    unsold_ids = {
        row[0] for row in db.query(Auction.player_id).filter(
            Auction.auction_type == a_type, Auction.status == AuctionStatus.unsold,
            Auction.player_id.in_(pool_ids),
        ).all()
    }
    fresh = [p for p in all_pool if p.id not in unsold_ids]
    return fresh if fresh else all_pool  # round complete - everyone's fair game again


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


def _redirect(auction_type: str, msg: str = None, snd: str = None):
    url = f"/admin/auction?auction_type={auction_type}"
    if msg:
        url += f"&msg={msg}"
    if snd:
        url += f"&snd={snd}"
    return RedirectResponse(url=url, status_code=303)


def _finalize_expired(db: Session, auction: Auction):
    """Called opportunistically on every poll. If the timer's run out, resolve
    the auction automatically: sold to the leader, or unsold if no bids."""
    if not auction or auction.status != AuctionStatus.live:
        return
    if auction.paused_remaining_seconds is not None or auction.timeout_team_id:
        return  # frozen - don't auto-expire while paused or a timeout is running
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


def _resume_from_pause(db: Session, auction: Auction):
    """Un-freezes the main timer, whether it was a manual pause or a team
    timeout: restores last_action_at so the deadline reflects the seconds
    that were left when it was frozen."""
    if auction.paused_remaining_seconds is None:
        return
    timer_seconds = get_settings(db).timer_seconds
    elapsed_to_restore = timer_seconds - auction.paused_remaining_seconds
    auction.last_action_at = datetime.utcnow() - timedelta(seconds=elapsed_to_restore)
    auction.paused_remaining_seconds = None


def _finalize_timeout(db: Session, auction: Auction):
    """Called opportunistically on every poll. If a team's timeout window has
    run out, auto-resume the main timer from where it was frozen."""
    if not auction or not auction.timeout_team_id or not auction.timeout_started_at:
        return
    deadline = auction.timeout_started_at + timedelta(seconds=get_settings(db).timeout_seconds)
    if datetime.utcnow() < deadline:
        return
    auction.timeout_team_id = None
    auction.timeout_started_at = None
    _resume_from_pause(db, auction)
    db.commit()


def _seconds_left(db: Session, auction: Auction, timer_seconds: int) -> int:
    """Seconds remaining on the main bidding timer, frozen at whatever it was
    if the timer's paused or a team timeout is running."""
    if auction.paused_remaining_seconds is not None:
        return auction.paused_remaining_seconds
    deadline = (auction.last_action_at or auction.started_at) + timedelta(seconds=timer_seconds)
    return max(0, int((deadline - datetime.utcnow()).total_seconds()))


def _timeout_seconds_left(db: Session, auction: Auction) -> int:
    if not auction.timeout_team_id or not auction.timeout_started_at:
        return 0
    deadline = auction.timeout_started_at + timedelta(seconds=get_settings(db).timeout_seconds)
    return max(0, int((deadline - datetime.utcnow()).total_seconds()))


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
    _finalize_timeout(db, live)
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
    settings = get_settings(db)
    timer_seconds = settings.timer_seconds
    seconds_left = _seconds_left(db, live, timer_seconds) if live else None
    can_undo = bool(live and live.bids)
    is_paused = bool(live and live.paused_remaining_seconds is not None and not live.timeout_team_id)
    is_timeout = bool(live and live.timeout_team_id)
    timeout_team = db.query(Team).filter(Team.id == live.timeout_team_id).first() if is_timeout else None
    timeout_seconds_left = _timeout_seconds_left(db, live) if is_timeout else None

    roll_counts = None
    roll_captain_count = None
    if not live and not pending:
        if a_type == AuctionType.captain:
            roll_captain_count = len(_eligible_pool(db, a_type))
        else:
            roll_counts = {c: len(_eligible_pool(db, a_type, c)) for c in SKILL_CATEGORIES}

    return templates.TemplateResponse(
        "admin/auction_console.html",
        {
            "request": request, "user": user, "live": live, "live_photo": live_photo,
            "pool": pool, "teams": teams, "auction_type": auction_type,
            "msg": msg, "min_next_bid": min_next_bid, "seconds_left": seconds_left,
            "timer_total": timer_seconds, "can_undo": can_undo, "pending": pending,
            "is_paused": is_paused, "is_timeout": is_timeout, "timeout_team": timeout_team,
            "timeout_seconds_left": timeout_seconds_left, "max_timeouts": settings.max_timeouts_per_team,
            "categories": SKILL_CATEGORIES, "roll_counts": roll_counts, "roll_captain_count": roll_captain_count,
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
    _finalize_timeout(db, live)
    _finalize_expired(db, live)
    if live and live.status != AuctionStatus.live:
        live = None
    timer_seconds = get_settings(db).timer_seconds
    seconds_left = None
    timeout_seconds_left = None
    timeout_team = None
    if live:
        seconds_left = _seconds_left(db, live, timer_seconds)
        if live.timeout_team_id:
            timeout_seconds_left = _timeout_seconds_left(db, live)
            timeout_team = db.query(Team).filter(Team.id == live.timeout_team_id).first()
    return templates.TemplateResponse(
        "admin/_timer_fragment.html",
        {"request": request, "live": live, "seconds_left": seconds_left, "timer_total": timer_seconds,
         "is_paused": bool(live and live.paused_remaining_seconds is not None and not live.timeout_team_id),
         "timeout_team": timeout_team, "timeout_seconds_left": timeout_seconds_left},
    )


@router.get("/admin/auction/state", response_class=HTMLResponse)
def admin_state(
    request: Request,
    auction_type: str = "player",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    _finalize_timeout(db, live)
    _finalize_expired(db, live)
    if live and live.status != AuctionStatus.live:
        live = None
    teams = db.query(Team).order_by(Team.id).all()
    min_next_bid = next_bid_amount(live, get_slabs(db)) if live else None
    can_undo = bool(live and live.bids)
    settings = get_settings(db)
    is_paused = bool(live and live.paused_remaining_seconds is not None and not live.timeout_team_id)
    is_timeout = bool(live and live.timeout_team_id)
    timeout_team = db.query(Team).filter(Team.id == live.timeout_team_id).first() if is_timeout else None
    return templates.TemplateResponse(
        "admin/_live_state_fragment.html",
        {"request": request, "live": live, "teams": teams, "auction_type": auction_type,
         "min_next_bid": min_next_bid, "can_undo": can_undo, "is_paused": is_paused, "is_timeout": is_timeout,
         "timeout_team": timeout_team, "max_timeouts": settings.max_timeouts_per_team},
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


@router.post("/admin/auction/{auction_id}/pause", response_class=HTMLResponse)
def pause_auction(
    auction_id: int,
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id, Auction.status == AuctionStatus.live).first()
    if not auction:
        return _redirect(auction_type, "Auction already closed")
    if auction.paused_remaining_seconds is None:
        auction.paused_remaining_seconds = _seconds_left(db, auction, get_settings(db).timer_seconds)
        db.commit()
    return _redirect(auction_type)


@router.post("/admin/auction/{auction_id}/resume", response_class=HTMLResponse)
def resume_auction(
    auction_id: int,
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id, Auction.status == AuctionStatus.live).first()
    if not auction:
        return _redirect(auction_type, "Auction already closed")
    auction.timeout_team_id = None
    auction.timeout_started_at = None
    _resume_from_pause(db, auction)
    db.commit()
    return _redirect(auction_type)


@router.post("/admin/auction/{auction_id}/timeout", response_class=HTMLResponse)
def start_timeout(
    auction_id: int,
    team_id: int = Form(...),
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id, Auction.status == AuctionStatus.live).first()
    if not auction:
        return _redirect(auction_type, "Auction already closed")
    if auction.paused_remaining_seconds is not None:
        return _redirect(auction_type, "Timer is already paused")

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        return _redirect(auction_type, "Team not found")
    settings = get_settings(db)
    if (team.timeouts_used or 0) >= (settings.max_timeouts_per_team or 0):
        return _redirect(auction_type, f"{team.name} has no timeouts left")

    auction.paused_remaining_seconds = _seconds_left(db, auction, settings.timer_seconds)
    auction.timeout_team_id = team.id
    auction.timeout_started_at = datetime.utcnow()
    team.timeouts_used = (team.timeouts_used or 0) + 1
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
    return _redirect(auction_type, snd="sold")


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
    return _redirect(auction_type, snd="unsold")


def _live_context(db: Session):
    live, pending = _current_auction(db)
    settings = get_settings(db)
    photo = _player_photo(db, live.player, live.current_team_id) if live else None
    seconds_left = None
    recent_bids = []
    is_paused = False
    timeout_team = None
    timeout_seconds_left = None
    if live:
        seconds_left = _seconds_left(db, live, settings.timer_seconds)
        is_paused = live.paused_remaining_seconds is not None and not live.timeout_team_id
        if live.timeout_team_id:
            timeout_team = db.query(Team).filter(Team.id == live.timeout_team_id).first()
            timeout_seconds_left = _timeout_seconds_left(db, live)
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

    return {
        "live": live, "photo": photo, "seconds_left": seconds_left, "teams": teams,
        "recent_bids": recent_bids, "sold_auctions": sold_auctions, "pending": pending,
        "reveal_seconds_left": reveal_seconds_left, "reveal_category": reveal_category,
        "ticker_speed": settings.ticker_speed_seconds, "timer_seconds": settings.timer_seconds,
        "resolved": resolved, "resolved_photo": resolved_photo,
        "is_paused": is_paused, "timeout_team": timeout_team, "timeout_seconds_left": timeout_seconds_left,
    }


def _next_auction_countdown(db: Session):
    """Idle-screen state, driven only by settings.captain_auction_at (the single
    auction date): 'countdown' before it, 'starting_now' same calendar day once
    it's passed, 'see_you_next_year' on any later day. No other rules."""
    settings = get_settings(db)
    auction_date = settings.captain_auction_at
    if not auction_date:
        return None, None
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    if now < auction_date:
        return "countdown", auction_date
    if now.date() == auction_date.date():
        return "starting_now", None
    return "see_you_next_year", None


@router.get("/auction/live", response_class=HTMLResponse)
def live_view_redirect():
    """/auction/live and /spectator/live used to be two copies of the same
    page (one login-gated, one public), kept in sync by hand on every
    change. Spectator is the one that stays - it's public (no login
    friction for the TV screen) and has no admin controls to protect."""
    return RedirectResponse(url="/spectator/live", status_code=307)
