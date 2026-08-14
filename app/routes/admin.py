from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Team, User, Role, Bid, Auction, AuctionStatus
from app.auth import require_role, hash_password, normalize_phone
from app.images import save_uploaded_image, slugify, IMAGES_DIR

router = APIRouter(prefix="/admin")
from app.templating import templates

super_admin_only = require_role(Role.super_admin)
staff_only = require_role(Role.super_admin, Role.admin)


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
    logo_file: UploadFile = File(None),
    primary_color: str = Form("#3d6ef0"),
    secondary_color: str = Form("#161a23"),
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
    team = Team(
        name=name, purse_total=purse_total, logo_url=None,
        primary_color=primary_color, secondary_color=secondary_color,
    )
    db.add(team)
    db.commit()

    if logo_file is not None and logo_file.filename:
        try:
            save_uploaded_image(logo_file, IMAGES_DIR / "teams", slugify(team.name))
        except ValueError:
            pass  # unsupported file type, team still saved - logo falls back to placeholder

    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse(
        "admin/_teams_list.html", {"request": request, "teams": teams, "error": None}
    )


@router.post("/teams/{team_id}/logo", response_class=HTMLResponse)
def upload_team_logo(
    team_id: int,
    request: Request,
    logo_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    error = None
    if team:
        try:
            save_uploaded_image(logo_file, IMAGES_DIR / "teams", slugify(team.name))
        except ValueError as e:
            error = str(e)
    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse(
        "admin/_teams_list.html", {"request": request, "teams": teams, "error": error}
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
    phone = normalize_phone(phone)
    if len(phone) != 10:
        return templates.TemplateResponse(
            "admin/_manager_form.html",
            {"request": request, "team": team, "error": "Enter a valid 10 digit phone number"},
        )

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


@router.get("/teams/{team_id}/roster", response_class=HTMLResponse)
def team_roster(
    team_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(super_admin_only)
):
    from app.routes.manager import roster_context

    team = db.query(Team).filter(Team.id == team_id).first()
    all_teams = db.query(Team).order_by(Team.id).all()
    ctx = roster_context(team)
    return templates.TemplateResponse(
        "manager/my_team.html",
        {"request": request, "user": user, "team": team, "is_own": False,
         "all_teams": all_teams, "switch_prefix": "/admin/teams", "switch_suffix": "/roster", **ctx},
    )


@router.get("/audit", response_class=HTMLResponse)
def audit_log(request: Request, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    bids = db.query(Bid).order_by(Bid.created_at.desc()).limit(200).all()
    total_bid_value = db.query(func.coalesce(func.sum(Auction.current_bid), 0)).filter(
        Auction.status == AuctionStatus.sold
    ).scalar()
    return templates.TemplateResponse(
        "admin/audit.html",
        {"request": request, "user": user, "bids": bids, "total_bid_value": total_bid_value},
    )
