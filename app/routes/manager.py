from datetime import datetime
from collections import Counter
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Team, Auction, AuctionStatus, Bid, User, Role, Player, PlayerRating
from app.auth import require_role, require_login
from app.bidding import next_bid_amount, purse_check
from app.app_settings import get_slabs
from app.routes.auction import _player_photo, _players_bought

router = APIRouter()
from app.templating import templates
manager_only = require_role(Role.manager, Role.captain)


def _my_team(db: Session, user: User):
    return db.query(Team).filter(Team.manager_id == user.id).first()


def roster_context(team: Team):
    skill_counts = Counter()
    avg_price = 0
    if team:
        for p in team.players:
            skill_counts[p.primary_skill or "Unspecified"] += 1
        priced = [p.sold_price for p in team.players if p.sold_price]
        avg_price = round(sum(priced) / len(priced)) if priced else 0
    return {"skill_counts": dict(skill_counts), "avg_price": avg_price}


@router.get("/my-team", response_class=HTMLResponse)
def my_team(request: Request, db: Session = Depends(get_db), user: User = Depends(manager_only)):
    team = _my_team(db, user)
    all_teams = db.query(Team).order_by(Team.id).all()
    ctx = roster_context(team)
    return templates.TemplateResponse(
        "manager/my_team.html",
        {"request": request, "user": user, "team": team, "is_own": True,
         "all_teams": all_teams, "switch_prefix": "/team", "switch_suffix": "", **ctx},
    )


@router.get("/teams", response_class=HTMLResponse)
def teams_index(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse("manager/teams_index.html", {"request": request, "user": user, "teams": teams})


@router.get("/team/{team_id}", response_class=HTMLResponse)
def view_team_roster(
    team_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)
):
    team = db.query(Team).filter(Team.id == team_id).first()
    all_teams = db.query(Team).order_by(Team.id).all()
    is_own = bool(team and team.manager_id == user.id)
    ctx = roster_context(team)
    return templates.TemplateResponse(
        "manager/my_team.html",
        {"request": request, "user": user, "team": team, "is_own": is_own,
         "all_teams": all_teams, "switch_prefix": "/team", "switch_suffix": "", **ctx},
    )


@router.get("/bid-panel", response_class=HTMLResponse)
def bid_panel_page(request: Request, db: Session = Depends(get_db), user: User = Depends(manager_only)):
    return templates.TemplateResponse("manager/bid_panel_page.html", {"request": request, "user": user})


@router.get("/bid-panel/fragment", response_class=HTMLResponse)
def bid_panel(request: Request, db: Session = Depends(get_db), user: User = Depends(manager_only)):
    team = _my_team(db, user)
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    photo = _player_photo(db, live.player, live.current_team_id) if live else None
    next_amount, disabled, disabled_reason = None, True, ""

    if live and team:
        next_amount = next_bid_amount(live, get_slabs(db))
        if live.current_team_id == team.id:
            disabled, disabled_reason = True, "You're already leading this bid"
        else:
            bought = _players_bought(db, team.id)
            err = purse_check(team, live.auction_type, next_amount, bought)
            disabled, disabled_reason = bool(err), (err or "")
    elif not team:
        disabled_reason = "No team assigned to your login yet"

    rating = None
    if live and team:
        rating = db.query(PlayerRating).filter(
            PlayerRating.team_id == team.id, PlayerRating.player_id == live.player_id
        ).first()

    return templates.TemplateResponse(
        "manager/_bid_panel.html",
        {"request": request, "live": live, "photo": photo, "team": team,
         "next_amount": next_amount, "disabled": disabled, "disabled_reason": disabled_reason,
         "rating": rating},
    )


@router.post("/bid-panel/bid", response_class=HTMLResponse)
def place_my_bid(request: Request, db: Session = Depends(get_db), user: User = Depends(manager_only)):
    team = _my_team(db, user)
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    if live and team and live.current_team_id != team.id:
        amount = next_bid_amount(live, get_slabs(db))
        bought = _players_bought(db, team.id)
        if not purse_check(team, live.auction_type, amount, bought):
            db.add(Bid(auction_id=live.id, team_id=team.id, amount=amount, entered_by_admin_id=user.id))
            live.current_bid = amount
            live.current_team_id = team.id
            live.last_action_at = datetime.utcnow()
            db.commit()
    return RedirectResponse(url="/bid-panel", status_code=303)


def _ratings_rows(db: Session, team_id: int):
    ratings_by_player = {
        r.player_id: r for r in db.query(PlayerRating).filter(PlayerRating.team_id == team_id).all()
    }
    players = db.query(Player).order_by(Player.id).all()
    rows = []
    for p in players:
        rows.append({"player": p, "rating": ratings_by_player.get(p.id)})
    return rows


@router.get("/player-ratings", response_class=HTMLResponse)
def player_ratings_page(request: Request, db: Session = Depends(get_db), user: User = Depends(manager_only)):
    team = _my_team(db, user)
    rows = _ratings_rows(db, team.id) if team else []
    return templates.TemplateResponse(
        "manager/player_ratings.html",
        {"request": request, "rows": rows, "team": team},
    )


@router.get("/player-ratings/{player_id}/edit", response_class=HTMLResponse)
def player_rating_edit_row(
    player_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(manager_only)
):
    team = _my_team(db, user)
    player = db.query(Player).filter(Player.id == player_id).first()
    rating = db.query(PlayerRating).filter(
        PlayerRating.team_id == team.id, PlayerRating.player_id == player_id
    ).first()
    return templates.TemplateResponse(
        "manager/_rating_row.html",
        {"request": request, "player": player, "rating": rating, "editing": True},
    )


@router.get("/player-ratings/{player_id}/cancel", response_class=HTMLResponse)
def player_rating_cancel_row(
    player_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(manager_only)
):
    team = _my_team(db, user)
    player = db.query(Player).filter(Player.id == player_id).first()
    rating = db.query(PlayerRating).filter(
        PlayerRating.team_id == team.id, PlayerRating.player_id == player_id
    ).first()
    return templates.TemplateResponse(
        "manager/_rating_row.html",
        {"request": request, "player": player, "rating": rating, "editing": False},
    )


@router.post("/player-ratings/{player_id}", response_class=HTMLResponse)
def player_rating_save(
    player_id: int,
    request: Request,
    batting: str = Form(""),
    bowling: str = Form(""),
    fielding: str = Form(""),
    overall: str = Form(""),
    pool_grade: str = Form(""),
    priority_level: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(manager_only),
):
    team = _my_team(db, user)
    player = db.query(Player).filter(Player.id == player_id).first()

    rating = db.query(PlayerRating).filter(
        PlayerRating.team_id == team.id, PlayerRating.player_id == player_id
    ).first()
    if not rating:
        rating = PlayerRating(team_id=team.id, player_id=player_id)
        db.add(rating)

    def _int_or_none(v):
        v = (v or "").strip()
        return int(v) if v.isdigit() else None

    rating.batting = _int_or_none(batting)
    rating.bowling = _int_or_none(bowling)
    rating.fielding = _int_or_none(fielding)
    rating.overall = _int_or_none(overall)
    rating.pool_grade = (pool_grade or "").strip() or None
    rating.priority_level = (priority_level or "").strip() or None
    db.commit()
    db.refresh(rating)

    return templates.TemplateResponse(
        "manager/_rating_row.html",
        {"request": request, "player": player, "rating": rating, "editing": False},
    )
