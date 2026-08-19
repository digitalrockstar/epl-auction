import random
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Team, TeamAssignment, User, Role
from app.auth import require_role
from app.templating import templates

router = APIRouter(prefix="/admin/team-reveal")
staff_only = require_role(Role.super_admin, Role.admin)

SLOTS = ["Team A", "Team B", "Team C", "Team D"]


def _ensure_slots(db: Session):
    existing = {a.slot_label for a in db.query(TeamAssignment).all()}
    for slot in SLOTS:
        if slot not in existing:
            db.add(TeamAssignment(slot_label=slot))
    db.commit()


def _state(db: Session):
    assignments = db.query(TeamAssignment).order_by(TeamAssignment.id).all()
    teams = db.query(Team).order_by(Team.name).all()
    rolled_slots = [a.slot_label for a in assignments if a.team_id]
    rolled_teams = [a.team_id for a in assignments if a.team_id]
    remaining_slots = [s for s in SLOTS if s not in rolled_slots]
    remaining_teams = [t for t in teams if t.id not in rolled_teams]
    return assignments, teams, remaining_slots, remaining_teams


@router.get("", response_class=HTMLResponse)
def page(request: Request, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    _ensure_slots(db)
    assignments, teams, remaining_slots, remaining_teams = _state(db)

    return templates.TemplateResponse(
        "admin/team_reveal.html",
        {
            "request": request, "user": user, "assignments": assignments,
            "remaining_slots": remaining_slots, "remaining_teams": remaining_teams,
            "rolls_done": len(SLOTS) - len(remaining_slots), "rolls_total": len(SLOTS),
        },
    )


@router.post("/roll")
def roll(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    _ensure_slots(db)
    assignments, teams, remaining_slots, remaining_teams = _state(db)

    if not remaining_slots or not remaining_teams:
        return JSONResponse({"done": True, "pairs": []})

    # If this roll leaves exactly one slot and one team, auto-pair the 4th
    # alongside the 3rd instead of waiting for a separate manual roll.
    auto_pair = len(remaining_slots) == 2

    chosen_slot = random.choice(remaining_slots)
    chosen_team = random.choice(remaining_teams)
    now = datetime.utcnow()
    row = next(a for a in assignments if a.slot_label == chosen_slot)
    row.team_id = chosen_team.id
    row.rolled_at = now
    pairs = [{"slot": chosen_slot, "team_id": chosen_team.id, "team_name": chosen_team.name, "logo_url": chosen_team.logo_url}]

    if auto_pair:
        last_slot = [s for s in remaining_slots if s != chosen_slot][0]
        last_team = [t for t in remaining_teams if t.id != chosen_team.id][0]
        last_row = next(a for a in assignments if a.slot_label == last_slot)
        last_row.team_id = last_team.id
        last_row.rolled_at = now
        pairs.append({"slot": last_slot, "team_id": last_team.id, "team_name": last_team.name, "logo_url": last_team.logo_url})

    db.commit()
    return JSONResponse({"done": False, "pairs": pairs, "remaining_slots": remaining_slots, "remaining_teams": [t.name for t in remaining_teams]})
