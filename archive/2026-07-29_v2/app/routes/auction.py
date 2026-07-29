from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player, Team, Auction, AuctionType, AuctionStatus, Bid, User, Role, PlayerTeamImage
from app.auth import require_role, require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
staff_only = require_role(Role.super_admin, Role.admin)


def _player_photo(db: Session, player: Player, team_id):
    if team_id:
        img = (
            db.query(PlayerTeamImage)
            .filter(PlayerTeamImage.player_id == player.id, PlayerTeamImage.team_id == team_id)
            .first()
        )
        if img:
            return img.image_url
    return player.profile_photo_url or ""


def _redirect(auction_type: str, msg: str = None):
    url = f"/admin/auction?auction_type={auction_type}"
    if msg:
        url += f"&msg={msg}"
    return RedirectResponse(url=url, status_code=303)


@router.get("/admin/auction", response_class=HTMLResponse)
def auction_console(
    request: Request,
    auction_type: str = "player",
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    a_type = AuctionType.captain if auction_type == "captain" else AuctionType.player
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()

    sold_ids = [row[0] for row in db.query(Auction.player_id).filter(Auction.status == AuctionStatus.sold)]
    query = db.query(Player).join(Player.user).filter(Player.id.notin_(sold_ids))
    if a_type == AuctionType.captain:
        pool = query.filter(Player.wants_captaincy == True, Player.team_id.is_(None)).all()  # noqa: E712
    else:
        pool = query.filter(Player.team_id.is_(None)).all()

    teams = db.query(Team).order_by(Team.id).all()
    live_photo = _player_photo(db, live.player, live.current_team_id) if live else None
    min_next_bid = None
    if live:
        min_next_bid = live.current_bid + 1 if live.current_team_id else live.base_price

    return templates.TemplateResponse(
        "admin/auction_console.html",
        {
            "request": request, "user": user, "live": live, "live_photo": live_photo,
            "pool": pool, "teams": teams, "auction_type": auction_type,
            "msg": msg, "min_next_bid": min_next_bid,
        },
    )


@router.post("/admin/auction/start/{player_id}", response_class=HTMLResponse)
def start_auction(
    player_id: int,
    auction_type: str = Form(...),
    base_price: int = Form(0),
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
    if base_price < 0:
        return _redirect(auction_type, "Base price cannot be negative")

    a_type = AuctionType.captain if auction_type == "captain" else AuctionType.player
    auction = Auction(
        auction_type=a_type, player_id=player_id, status=AuctionStatus.live,
        base_price=base_price, current_bid=base_price, started_at=datetime.utcnow(),
    )
    db.add(auction)
    db.commit()
    return _redirect(auction_type)


@router.post("/admin/auction/{auction_id}/bid", response_class=HTMLResponse)
def place_bid(
    auction_id: int,
    team_id: int = Form(...),
    amount: int = Form(...),
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id, Auction.status == AuctionStatus.live).first()
    if not auction:
        return _redirect(auction_type, "This auction is no longer live")

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        return _redirect(auction_type, "Team not found")

    floor = auction.current_bid + 1 if auction.current_team_id else auction.base_price
    if amount < floor:
        return _redirect(auction_type, f"Bid must be at least {floor}")

    if auction.auction_type == AuctionType.player and amount > team.purse_remaining:
        return _redirect(auction_type, f"{team.name} only has {team.purse_remaining} left in purse")

    db.add(Bid(auction_id=auction.id, team_id=team_id, amount=amount, entered_by_admin_id=user.id))
    auction.current_bid = amount
    auction.current_team_id = team_id
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
    if auction.auction_type == AuctionType.player and auction.current_bid > team.purse_remaining:
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
    return _redirect(auction_type)


@router.get("/auction/live", response_class=HTMLResponse)
def live_view(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    photo = _player_photo(db, live.player, live.current_team_id) if live else None
    return templates.TemplateResponse(
        "auction/live.html", {"request": request, "live": live, "photo": photo}
    )


@router.get("/auction/live/fragment", response_class=HTMLResponse)
def live_fragment(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    photo = _player_photo(db, live.player, live.current_team_id) if live else None
    return templates.TemplateResponse(
        "auction/_live_fragment.html", {"request": request, "live": live, "photo": photo}
    )
