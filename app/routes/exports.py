from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import require_role
from app.models import User, Team, Player, Auction, AuctionStatus, Match, Role
from app.pdf_export import team_rosters_pdf, auction_summary_pdf, points_schedule_pdf, player_detail_pdf

router = APIRouter(prefix="/admin/export")
staff_only = require_role(Role.super_admin, Role.admin)


def _pdf(content: bytes, filename: str) -> Response:
    return Response(content=content, media_type="application/pdf",
                     headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/rosters.pdf")
def export_rosters(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    teams = db.query(Team).order_by(Team.id).all()
    return _pdf(team_rosters_pdf(teams), "epl-rosters.pdf")


@router.get("/roster/{team_id}.pdf")
def export_roster(team_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        return Response(status_code=404)
    return _pdf(team_rosters_pdf([team]), f"epl-{team.name.lower().replace(' ', '-')}-roster.pdf")


@router.get("/auction-summary.pdf")
def export_auction_summary(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    sold = db.query(Auction).filter(Auction.status == AuctionStatus.sold).all()
    unsold = db.query(Auction).filter(Auction.status == AuctionStatus.unsold).all()
    return _pdf(auction_summary_pdf(sold, unsold), "epl-auction-summary.pdf")


@router.get("/points-schedule.pdf")
def export_points_schedule(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    matches = db.query(Match).order_by(Match.match_number).all()
    teams = db.query(Team).order_by(Team.id).all()
    standings = {t.id: {"name": t.name, "played": 0, "won": 0, "lost": 0, "points": 0} for t in teams}
    for m in matches:
        if not m.winner_team_id:
            continue
        loser_id = m.team_b_id if m.winner_team_id == m.team_a_id else m.team_a_id
        for tid in (m.team_a_id, m.team_b_id):
            if tid in standings:
                standings[tid]["played"] += 1
        if m.winner_team_id in standings:
            standings[m.winner_team_id]["won"] += 1
            standings[m.winner_team_id]["points"] += 2
        if loser_id in standings:
            standings[loser_id]["lost"] += 1
    ordered = sorted(standings.values(), key=lambda s: (-s["points"], s["name"]))
    return _pdf(points_schedule_pdf(matches, ordered), "epl-points-schedule.pdf")


@router.get("/player/{player_id}.pdf")
def export_player(player_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        return Response(status_code=404)
    return _pdf(player_detail_pdf(player), f"epl-{player.user.name.lower().replace(' ', '-')}.pdf")
