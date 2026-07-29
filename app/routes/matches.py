from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from collections import defaultdict

from app.database import get_db
from app.models import Match, PlayingXI, Team, Player, User, Role
from app.auth import require_role

router = APIRouter(prefix="/admin/matches")
templates = Jinja2Templates(directory="app/templates")
staff_only = require_role(Role.super_admin, Role.admin)


def _points_table(db: Session):
    teams = db.query(Team).all()
    table = {t.id: {"team": t, "played": 0, "won": 0, "lost": 0, "points": 0} for t in teams}
    for m in db.query(Match).filter(Match.winner_team_id.isnot(None)).all():
        for tid in (m.team_a_id, m.team_b_id):
            if tid in table:
                table[tid]["played"] += 1
        if m.winner_team_id in table:
            table[m.winner_team_id]["won"] += 1
            table[m.winner_team_id]["points"] += 2
        loser_id = m.team_b_id if m.winner_team_id == m.team_a_id else m.team_a_id
        if loser_id in table:
            table[loser_id]["lost"] += 1
    return sorted(table.values(), key=lambda r: (-r["points"], r["team"].name))


@router.get("", response_class=HTMLResponse)
def matches_page(request: Request, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    teams = db.query(Team).order_by(Team.id).all()
    matches = db.query(Match).order_by(Match.match_number).all()
    xi_counts = defaultdict(int)
    for row in db.query(PlayingXI.player_id).all():
        xi_counts[row[0]] += 1
    under_min = [
        p for p in db.query(Player).filter(Player.team_id.isnot(None)).all()
        if xi_counts.get(p.id, 0) < 2
    ]
    return templates.TemplateResponse(
        "admin/matches.html",
        {
            "request": request, "user": user, "teams": teams, "matches": matches,
            "points_table": _points_table(db), "under_min": under_min, "xi_counts": xi_counts,
        },
    )


@router.post("", response_class=HTMLResponse)
def create_match(
    match_number: int = Form(...),
    match_type: str = Form("league"),
    team_a_id: int = Form(...),
    team_b_id: int = Form(...),
    match_date: str = Form(...),
    ground_fee: int = Form(8500),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    if team_a_id != team_b_id:
        db.add(Match(
            match_number=match_number, match_type=match_type, team_a_id=team_a_id, team_b_id=team_b_id,
            match_date=datetime.fromisoformat(match_date), ground_fee=ground_fee,
        ))
        db.commit()
    return RedirectResponse(url="/admin/matches", status_code=303)


@router.post("/{match_id}/result", response_class=HTMLResponse)
def record_result(match_id: int, winner_team_id: int = Form(...), db: Session = Depends(get_db), user: User = Depends(staff_only)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if match and winner_team_id in (match.team_a_id, match.team_b_id):
        match.winner_team_id = winner_team_id
        db.commit()
    return RedirectResponse(url="/admin/matches", status_code=303)


@router.post("/{match_id}/xi", response_class=HTMLResponse)
def record_xi(match_id: int, player_ids: str = Form(...), db: Session = Depends(get_db), user: User = Depends(staff_only)):
    ids = [int(x) for x in player_ids.split(",") if x.strip().isdigit()]
    db.query(PlayingXI).filter(PlayingXI.match_id == match_id).delete()
    for pid in ids:
        db.add(PlayingXI(match_id=match_id, player_id=pid))
    db.commit()
    return RedirectResponse(url="/admin/matches", status_code=303)
