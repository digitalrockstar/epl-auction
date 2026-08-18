from datetime import datetime
from collections import Counter
import csv
import io
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Team, Auction, AuctionStatus, Bid, User, Role, Player, PlayerRating
from app.auth import require_role, require_login
from app.bidding import next_bid_amount, purse_check
from app.config import MIN_SQUAD_SIZE, PLAYER_BASE_PRICE
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

    max_bid_allowed = None
    if team:
        bought_for_max = _players_bought(db, team.id)
        remaining_needed = MIN_SQUAD_SIZE - (bought_for_max + 1)
        reserve = max(remaining_needed, 0) * PLAYER_BASE_PRICE
        max_bid_allowed = max(team.purse_remaining - reserve, 0)

    return templates.TemplateResponse(
        "manager/_bid_panel.html",
        {"request": request, "live": live, "photo": photo, "team": team,
         "next_amount": next_amount, "disabled": disabled, "disabled_reason": disabled_reason,
         "rating": rating, "max_bid_allowed": max_bid_allowed},
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
    return bid_panel(request, db, user)


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
        {"request": request, "rows": rows, "team": team, "user": user},
    )


@router.get("/player-ratings/template.csv")
def player_ratings_template_csv(db: Session = Depends(get_db), user: User = Depends(manager_only)):
    team = _my_team(db, user)
    rows = _ratings_rows(db, team.id) if team else []

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["player_id", "player_name", "skill", "batting", "bowling", "fielding", "overall", "pool_grade", "max_budget"])
    for row in rows:
        p, r = row["player"], row["rating"]
        writer.writerow([
            p.id, p.user.name, p.primary_skill or "",
            r.batting if r and r.batting is not None else "",
            r.bowling if r and r.bowling is not None else "",
            r.fielding if r and r.fielding is not None else "",
            r.overall if r and r.overall is not None else "",
            r.pool_grade or "" if r else "",
            r.max_budget if r and r.max_budget is not None else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=player_ratings_template.csv"},
    )


@router.post("/player-ratings/upload")
def player_ratings_upload(
    request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(manager_only)
):
    team = _my_team(db, user)
    if not team:
        return RedirectResponse(url="/player-ratings", status_code=303)

    def _int_or_none(v, lo, hi):
        v = (v or "").strip()
        if not v.isdigit():
            return None
        return max(lo, min(hi, int(v)))

    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    existing = {r.player_id: r for r in db.query(PlayerRating).filter(PlayerRating.team_id == team.id).all()}
    valid_player_ids = {p.id for p in db.query(Player.id).all()}

    for line in reader:
        pid = (line.get("player_id") or "").strip()
        if not pid.isdigit() or int(pid) not in valid_player_ids:
            continue
        pid = int(pid)
        rating = existing.get(pid)
        if not rating:
            rating = PlayerRating(team_id=team.id, player_id=pid)
            db.add(rating)
            existing[pid] = rating
        rating.batting = _int_or_none(line.get("batting"), 0, 10)
        rating.bowling = _int_or_none(line.get("bowling"), 0, 10)
        rating.fielding = _int_or_none(line.get("fielding"), 0, 10)
        rating.overall = _int_or_none(line.get("overall"), 0, 10)
        grade = (line.get("pool_grade") or "").strip().upper()
        rating.pool_grade = grade if grade in ("A", "B", "C", "D") else None
        mb = (line.get("max_budget") or "").strip()
        rating.max_budget = int(mb) if mb.isdigit() else None

    db.commit()
    return RedirectResponse(url="/player-ratings", status_code=303)


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
    max_budget: str = Form(""),
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

    def _int_or_none(v, lo, hi):
        v = (v or "").strip()
        if not v.isdigit():
            return None
        n = int(v)
        return max(lo, min(hi, n))

    rating.batting = _int_or_none(batting, 0, 10)
    rating.bowling = _int_or_none(bowling, 0, 10)
    rating.fielding = _int_or_none(fielding, 0, 10)
    rating.overall = _int_or_none(overall, 0, 10)
    rating.pool_grade = pool_grade if pool_grade in ("A", "B", "C", "D") else None
    mb = (max_budget or "").strip()
    rating.max_budget = int(mb) if mb.isdigit() else None
    db.commit()
    db.refresh(rating)

    return templates.TemplateResponse(
        "manager/_rating_row.html",
        {"request": request, "player": player, "rating": rating, "editing": False},
    )
