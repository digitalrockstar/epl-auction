from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role
from app.auth import require_role
from app.app_settings import get_settings, get_slabs, slabs_to_json
from app.reset_logic import reset_auction_data

router = APIRouter(prefix="/admin/settings")
from app.templating import templates
super_admin_only = require_role(Role.super_admin)


@router.get("", response_class=HTMLResponse)
def settings_page(
    request: Request, msg: str = "", db: Session = Depends(get_db), user: User = Depends(super_admin_only)
):
    settings = get_settings(db)
    slabs = get_slabs(db)
    return templates.TemplateResponse(
        "admin/settings.html",
        {"request": request, "user": user, "settings": settings, "slabs": slabs, "msg": msg},
    )


@router.post("/general", response_class=HTMLResponse)
def update_general(
    telegram_enabled: str = Form(None),
    ticker_speed_seconds: int = Form(...),
    ticker_window: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    settings = get_settings(db)
    settings.telegram_enabled = telegram_enabled == "on"
    settings.ticker_speed_seconds = max(5, ticker_speed_seconds)
    settings.ticker_window = max(1, ticker_window)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=" + quote("Settings saved"), status_code=303)


@router.post("/slabs", response_class=HTMLResponse)
async def update_slabs(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    form = await request.form()
    rows = []
    i = 1
    while f"increment_{i}" in form:
        increment = int(form[f"increment_{i}"])
        ceiling_raw = form.get(f"ceiling_{i}")
        ceiling = float("inf") if not ceiling_raw else float(ceiling_raw)
        rows.append((ceiling, increment))
        i += 1

    if not rows:
        msg = quote("No slabs submitted, nothing changed")
        return RedirectResponse(url=f"/admin/settings?msg={msg}", status_code=303)

    rows.sort(key=lambda pair: pair[0])
    settings = get_settings(db)
    settings.increment_slabs = slabs_to_json(rows)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=" + quote("Bidding slabs updated"), status_code=303)


@router.post("/reset", response_class=HTMLResponse)
def reset_all(
    confirm: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    if confirm != "RESET":
        return RedirectResponse(
            url="/admin/settings?msg=" + quote("Type RESET exactly to confirm, nothing was touched"),
            status_code=303,
        )
    counts = reset_auction_data(db)
    msg = (
        f"Reset done. {counts['bids']} bids, {counts['auctions']} auctions, {counts['matches']} matches "
        f"cleared. {counts['players_reset']} players and {counts['teams_reset']} teams reset to unsold. "
        f"Players, managers, teams, and admin logins were kept."
    )
    return RedirectResponse(url="/admin/settings?msg=" + quote(msg), status_code=303)
