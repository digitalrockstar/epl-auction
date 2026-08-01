import csv
import io
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player, User, Role, Team, PlayerTeamImage
from app.auth import require_role, hash_password, normalize_phone, require_login
from app.images import save_uploaded_image, slugify, IMAGES_DIR

router = APIRouter(prefix="/admin/players")
profile_router = APIRouter(prefix="/players")
from app.templating import templates
staff_only = require_role(Role.super_admin, Role.admin)

REG_HEADERS = {
    "name": "Full Name",
    "phone": "Whatsapp Number",
    "primary_skill": "Primary Cricketing Skill",
    "batting_position": "Batting Position",
    "batting_hand": "Batting Hand",
    "bowling_style": "Bowling Style",
    "bowling_hand": "Bowling Hand",
    "wicketkeeping": "Wicketkeeping.",
    "wants_captaincy": "Want to be a Captain?",
    "experience_level": "Experience Level",
    "brief": "Short brief about your cricketing skills",
    "photo": "Clear Front View Profile Photo",
}

STATS_INT_FIELDS = [
    "matches_won", "matches_lost",
    "bat_matches", "bat_innings", "bat_runs", "bat_4s", "bat_6s", "bat_30s", "bat_ducks",
    "bowl_matches", "bowl_innings", "bowl_wickets", "bowl_3wkts", "bowl_dots", "bowl_extras",
    "bowl_4s_given", "bowl_6s_given", "field_catches", "field_runouts",
]
STATS_FLOAT_FIELDS = ["bat_sr", "bat_avg", "bowl_economy"]
# CSV header for each stats field is the same as the attribute name, admin can rename
# the export columns to match these before upload, or edit this mapping.
STATS_HEADER_MAP = {f: f for f in STATS_INT_FIELDS + STATS_FLOAT_FIELDS}


def _truthy(val: str) -> bool:
    return (val or "").strip().lower() in ("yes", "y", "true", "1")


@router.get("", response_class=HTMLResponse)
def players_page(request: Request, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    players = db.query(Player).order_by(Player.id).all()
    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse(
        "admin/players.html",
        {"request": request, "user": user, "players": players, "teams": teams, "message": None},
    )


@router.post("/import-registrations", response_class=HTMLResponse)
def import_registrations(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    try:
        content = file.file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    except Exception:
        players = db.query(Player).order_by(Player.id).all()
        teams = db.query(Team).order_by(Team.id).all()
        return templates.TemplateResponse(
            "admin/players.html",
            {"request": request, "user": user, "players": players, "teams": teams,
             "message": "Could not read that file, make sure it's a valid CSV export."},
        )

    created, skipped = 0, 0
    for row in rows:
        phone = normalize_phone(row.get(REG_HEADERS["phone"]))
        name = (row.get(REG_HEADERS["name"]) or "").strip()
        if not phone or not name or len(phone) != 10:
            skipped += 1
            continue

        existing_user = db.query(User).filter(User.phone == phone).first()
        if existing_user:
            skipped += 1
            continue

        u = User(name=name, phone=phone, password_hash=hash_password(phone[-6:]), role=Role.player)
        db.add(u)
        db.flush()

        p = Player(
            user_id=u.id,
            primary_skill=row.get(REG_HEADERS["primary_skill"]),
            batting_position=row.get(REG_HEADERS["batting_position"]),
            batting_hand=row.get(REG_HEADERS["batting_hand"]),
            bowling_style=row.get(REG_HEADERS["bowling_style"]),
            bowling_hand=row.get(REG_HEADERS["bowling_hand"]),
            is_wicketkeeper=_truthy(row.get(REG_HEADERS["wicketkeeping"])),
            wants_captaincy=_truthy(row.get(REG_HEADERS["wants_captaincy"])),
            experience_level=row.get(REG_HEADERS["experience_level"]),
            brief=row.get(REG_HEADERS["brief"]),
            profile_photo_url=row.get(REG_HEADERS["photo"]),
        )
        db.add(p)
        created += 1

    db.commit()
    players = db.query(Player).order_by(Player.id).all()
    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse(
        "admin/players.html",
        {
            "request": request, "user": user, "players": players, "teams": teams,
            "message": f"Imported {created} players, skipped {skipped} (duplicate phone or missing data).",
        },
    )


@router.post("/import-stats", response_class=HTMLResponse)
def import_stats(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    try:
        content = file.file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    except Exception:
        players = db.query(Player).order_by(Player.id).all()
        teams = db.query(Team).order_by(Team.id).all()
        return templates.TemplateResponse(
            "admin/players.html",
            {"request": request, "user": user, "players": players, "teams": teams,
             "message": "Could not read that file, make sure it's a valid CSV export."},
        )

    updated, unmatched = 0, 0
    for row in rows:
        phone = normalize_phone(row.get("Whatsapp Number") or row.get("phone") or "")
        if not phone:
            unmatched += 1
            continue
        u = db.query(User).filter(User.phone == phone).first()
        if not u or not u.player_profile:
            unmatched += 1
            continue

        p = u.player_profile
        for field in STATS_INT_FIELDS:
            raw = row.get(STATS_HEADER_MAP[field])
            if raw not in (None, ""):
                try:
                    setattr(p, field, int(float(raw)))
                except ValueError:
                    pass
        for field in STATS_FLOAT_FIELDS:
            raw = row.get(STATS_HEADER_MAP[field])
            if raw not in (None, ""):
                try:
                    setattr(p, field, float(raw))
                except ValueError:
                    pass
        updated += 1

    db.commit()
    players = db.query(Player).order_by(Player.id).all()
    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse(
        "admin/players.html",
        {
            "request": request, "user": user, "players": players, "teams": teams,
            "message": f"Updated stats for {updated} players, {unmatched} unmatched.",
        },
    )


@router.post("/{player_id}/photo", response_class=HTMLResponse)
def upload_main_photo(
    player_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    player = db.query(Player).filter(Player.id == player_id).first()
    message = "Photo saved."
    if player:
        phone = "".join(ch for ch in (player.user.phone or "") if ch.isdigit())
        try:
            save_uploaded_image(file, IMAGES_DIR / "players" / "main", phone)
        except ValueError as e:
            message = str(e)
    else:
        message = "Player not found."

    players = db.query(Player).order_by(Player.id).all()
    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse(
        "admin/players.html",
        {"request": request, "user": user, "players": players, "teams": teams, "message": message},
    )


@router.post("/{player_id}/kit-image", response_class=HTMLResponse)
def set_kit_image(
    player_id: int,
    request: Request,
    team_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
):
    player = db.query(Player).filter(Player.id == player_id).first()
    team = db.query(Team).filter(Team.id == team_id).first()
    message = "Kit photo saved."
    if player and team:
        phone = "".join(ch for ch in (player.user.phone or "") if ch.isdigit())
        try:
            save_uploaded_image(file, IMAGES_DIR / "players" / slugify(team.name), phone)
        except ValueError as e:
            message = str(e)
    else:
        message = "Player or team not found."

    players = db.query(Player).order_by(Player.id).all()
    teams = db.query(Team).order_by(Team.id).all()
    return templates.TemplateResponse(
        "admin/players.html",
        {"request": request, "user": user, "players": players, "teams": teams, "message": message},
    )


@profile_router.get("", response_class=HTMLResponse)
def players_list_view_only(
    tab: str = "players",
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
):
    my_team = None
    if user.role == Role.manager:
        my_team = user.managed_team
    elif user.role == Role.captain and user.player_profile:
        my_team = user.player_profile.team
    show_captain_tab = not (my_team and my_team.captain_id)

    tab = tab if tab in ("players", "captains") else "players"
    if tab == "captains" and not show_captain_tab:
        tab = "players"

    query = db.query(Player).order_by(Player.id)
    if tab == "captains":
        query = query.filter(Player.wants_captaincy.is_(True))
    players = query.all()

    return templates.TemplateResponse(
        "players/list.html",
        {"request": request, "user": user, "players": players, "tab": tab, "show_captain_tab": show_captain_tab},
    )


@profile_router.get("/{player_id}", response_class=HTMLResponse)
def player_profile(
    player_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)
):
    player = db.query(Player).filter(Player.id == player_id).first()
    show_phone = user.role in (Role.super_admin, Role.admin)
    return templates.TemplateResponse(
        "players/profile.html", {"request": request, "player": player, "show_phone": show_phone}
    )
