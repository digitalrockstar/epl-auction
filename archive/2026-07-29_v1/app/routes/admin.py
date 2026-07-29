from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Team, User, Role
from app.auth import require_role, hash_password

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")

super_admin_only = require_role(Role.super_admin)


@router.get("/teams", response_class=HTMLResponse)
def teams_page(request: Request, db: Session = Depends(get_db), user: User = Depends(super_admin_only)):
    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse(
        "admin/teams.html", {"request": request, "user": user, "teams": teams, "error": None}
    )


@router.post("/teams", response_class=HTMLResponse)
def create_team(
    request: Request,
    name: str = Form(...),
    purse_total: int = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    existing = db.query(Team).filter(Team.name == name).first()
    teams = db.query(Team).order_by(Team.id).all()
    if existing:
        return templates.TemplateResponse(
            "admin/_teams_list.html",
            {"request": request, "teams": teams, "error": f"Team '{name}' already exists"},
        )
    team = Team(name=name, purse_total=purse_total)
    db.add(team)
    db.commit()
    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse(
        "admin/_teams_list.html", {"request": request, "teams": teams, "error": None}
    )


@router.get("/teams/{team_id}/manager-form", response_class=HTMLResponse)
def manager_form(
    team_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(super_admin_only)
):
    team = db.query(Team).filter(Team.id == team_id).first()
    return templates.TemplateResponse(
        "admin/_manager_form.html", {"request": request, "team": team, "error": None}
    )


@router.post("/teams/{team_id}/manager", response_class=HTMLResponse)
def assign_manager(
    team_id: int,
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    team = db.query(Team).filter(Team.id == team_id).first()

    existing_phone = db.query(User).filter(User.phone == phone).first()
    if existing_phone:
        return templates.TemplateResponse(
            "admin/_manager_form.html",
            {"request": request, "team": team, "error": f"Phone {phone} is already registered"},
        )

    manager = User(name=name, phone=phone, password_hash=hash_password(password), role=Role.manager)
    db.add(manager)
    db.flush()  # get manager.id before commit
    team.manager_id = manager.id
    db.commit()
    db.refresh(team)

    return templates.TemplateResponse("admin/_team_row.html", {"request": request, "team": team})
