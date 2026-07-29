from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player, Team, Auction, AuctionType, AuctionStatus, Bid, User, Role, PlayerTeamImage
from app.auth import require_role, require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
staff_only = require_role(Role.super_admin, Role.admin)


def _player_photo(db: Session, player: Player, team_id: int | None) -> str:
    if team_id:
        img = (
            db.query(PlayerTeamImage)
            .filter(PlayerTeamImage.player_id == player.id, PlayerTeamImage.team_id == team_id)
            .first()
        )
        if img:
            return img.image_url
    return player.profile_photo_url or ""


@router.get("/admin/auction", response_class=HTMLResponse)
def auction_console(
    request: Request,
    auction_type: str = "player",
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    a_type = AuctionType.captain if auction_type == "captain" else AuctionType.player
    live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()

    sold_ids = [row[0] for row in db.query(Auction.player_id).filter(Auction.status == AuctionStatus.sold)]
    query = db.query(Player).join(Player.user).filter(Player.id.notin_(sold_ids))
    if a_type == AuctionType.captain:
        pool = query.filter(Player.wants_captaincy == True).all()  # noqa: E712
    else:
        pool = query.filter(Player.team_id.is_(None)).all()

    teams = db.query(Team).order_by(Team.id).all()
    live_photo = _player_photo(db, live.player, live.current_team_id) if live else None

    return templates.TemplateResponse(
        "admin/auction_console.html",
        {
            "request": request, "user": user, "live": live, "live_photo": live_photo,
            "pool": pool, "teams": teams, "auction_type": auction_type,
        },
    )


@router.post("/admin/auction/start/{player_id}", response_class=HTMLResponse)
def start_auction(
    player_id: int,
    request: Request,
    auction_type: str = Form(...),
    base_price: int = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    existing_live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
    if existing_live:
        return RedirectResponse_or_console(request, db, user, auction_type)

    a_type = AuctionType.captain if auction_type == "captain" else AuctionType.player
    auction = Auction(
        auction_type=a_type, player_id=player_id, status=AuctionStatus.live,
        base_price=base_price, current_bid=base_price, started_at=datetime.utcnow(),
    )
    db.add(auction)
    db.commit()
    return RedirectResponse_or_console(request, db, user, auction_type)


@router.post("/admin/auction/{auction_id}/bid", response_class=HTMLResponse)
def place_bid(
    auction_id: int,
    request: Request,
    team_id: int = Form(...),
    amount: int = Form(...),
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id, Auction.status == AuctionStatus.live).first()
    if auction:
        db.add(Bid(auction_id=auction.id, team_id=team_id, amount=amount, entered_by_admin_id=user.id))
        auction.current_bid = amount
        auction.current_team_id = team_id
        db.commit()
    return RedirectResponse_or_console(request, db, user, auction_type)


@router.post("/admin/auction/{auction_id}/sold", response_class=HTMLResponse)
def mark_sold(
    auction_id: int,
    request: Request,
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id).first()
    if auction and auction.current_team_id:
        auction.status = AuctionStatus.sold
        auction.closed_at = datetime.utcnow()
        player = auction.player
        team = db.query(Team).filter(Team.id == auction.current_team_id).first()
        player.sold_price = auction.current_bid

        if auction.auction_type == AuctionType.captain:
            player.is_captain = True
            player.team_id = team.id
            team.captain_id = player.id
        else:
            player.team_id = team.id
            team.purse_spent = (team.purse_spent or 0) + auction.current_bid
        db.commit()
    return RedirectResponse_or_console(request, db, user, auction_type)


@router.post("/admin/auction/{auction_id}/unsold", response_class=HTMLResponse)
def mark_unsold(
    auction_id: int,
    request: Request,
    auction_type: str = Form("player"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    auction = db.query(Auction).filter(Auction.id == auction_id).first()
    if auction:
        auction.status = AuctionStatus.unsold
        auction.closed_at = datetime.utcnow()
        db.commit()
    return RedirectResponse_or_console(request, db, user, auction_type)


def RedirectResponse_or_console(request, db, user, auction_type):
    # Re-render console directly instead of a redirect, keeps admin's place in the flow.
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/admin/auction?auction_type={auction_type}", status_code=303)


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
