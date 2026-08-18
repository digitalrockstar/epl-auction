from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from collections import defaultdict
from typing import Optional

from app.database import get_db
from app.models import Match, PlayingXI, Team, Player, User, Role
from app.auth import require_role
from app.config import GROUNDS
from app.match_stats import determine_winner, has_result, effective_balls, balls_to_decimal_overs

router = APIRouter(prefix="/admin/matches")
from app.templating import templates
staff_only = require_role(Role.super_admin, Role.admin)


def _points_table(db: Session):
    teams = db.query(Team).all()
    table = {
        t.id: {
            "team": t, "played": 0, "won": 0, "lost": 0, "tied": 0, "points": 0,
            "runs_for": 0, "balls_for": 0, "runs_against": 0, "balls_against": 0,
        }
        for t in teams
    }
    matches = db.query(Match).all()

    for m in matches:
        if m.winner_team_id in table:
            table[m.winner_team_id]["played"] += 1
            table[m.winner_team_id]["won"] += 1
            table[m.winner_team_id]["points"] += 2
            loser_id = m.team_b_id if m.winner_team_id == m.team_a_id else m.team_a_id
            if loser_id in table:
                table[loser_id]["played"] += 1
                table[loser_id]["lost"] += 1

        if has_result(m):
            eff_a = effective_balls(m.team_a_overs, m.team_a_wickets)
            eff_b = effective_balls(m.team_b_overs, m.team_b_wickets)
            if m.team_a_id in table:
                row = table[m.team_a_id]
                row["runs_for"] += m.team_a_runs
                row["balls_for"] += eff_a
                row["runs_against"] += m.team_b_runs
                row["balls_against"] += eff_b
            if m.team_b_id in table:
                row = table[m.team_b_id]
                row["runs_for"] += m.team_b_runs
                row["balls_for"] += eff_b
                row["runs_against"] += m.team_a_runs
                row["balls_against"] += eff_a

    rows = list(table.values())
    for row in rows:
        overs_for = balls_to_decimal_overs(row["balls_for"])
        overs_against = balls_to_decimal_overs(row["balls_against"])
        rr_for = (row["runs_for"] / overs_for) if overs_for else 0
        rr_against = (row["runs_against"] / overs_against) if overs_against else 0
        row["nrr"] = round(rr_for - rr_against, 3)
    return sorted(rows, key=lambda r: (-r["points"], -r["nrr"], r["team"].name))


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
            "grounds": GROUNDS,
        },
    )


@router.post("", response_class=HTMLResponse)
def create_match(
    match_number: int = Form(...),
    match_type: str = Form("league"),
    team_a_id: int = Form(...),
    team_b_id: int = Form(...),
    match_date: str = Form(...),
    ground: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    if team_a_id != team_b_id:
        db.add(Match(
            match_number=match_number, match_type=match_type, team_a_id=team_a_id, team_b_id=team_b_id,
            match_date=datetime.fromisoformat(match_date), ground=ground,
        ))
        db.commit()
    return RedirectResponse(url="/admin/matches", status_code=303)


@router.post("/{match_id}/scorecard", response_class=HTMLResponse)
def record_scorecard(
    match_id: int,
    team_a_runs: int = Form(...),
    team_a_overs: float = Form(...),
    team_a_wickets: int = Form(...),
    team_b_runs: int = Form(...),
    team_b_overs: float = Form(...),
    team_b_wickets: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if match:
        match.team_a_runs = team_a_runs
        match.team_a_overs = team_a_overs
        match.team_a_wickets = team_a_wickets
        match.team_b_runs = team_b_runs
        match.team_b_overs = team_b_overs
        match.team_b_wickets = team_b_wickets
        winner_id, is_tie = determine_winner(match)
        match.winner_team_id = winner_id
        db.commit()
    return RedirectResponse(url="/admin/matches", status_code=303)


@router.post("/{match_id}/result", response_class=HTMLResponse)
def record_result(match_id: int, winner_team_id: int = Form(...), db: Session = Depends(get_db), user: User = Depends(staff_only)):
    """Manual winner override — used to resolve a tied scorecard (super over)."""
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

