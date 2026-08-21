from datetime import datetime
from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role
from app.auth import require_role
from app.app_settings import get_settings, get_slabs, slabs_to_json
from app.reset_logic import reset_auction_data, reset_since

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


@router.post("/telegram", response_class=HTMLResponse)
def update_telegram(
    telegram_enabled: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    settings = get_settings(db)
    settings.telegram_enabled = telegram_enabled == "on"
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=" + quote("Telegram setting saved"), status_code=303)


@router.post("/timer", response_class=HTMLResponse)
def update_timer(
    timer_seconds: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    settings = get_settings(db)
    settings.timer_seconds = max(10, timer_seconds)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=" + quote("Timer duration saved"), status_code=303)


@router.post("/ticker", response_class=HTMLResponse)
def update_ticker(
    ticker_speed_seconds: int = Form(...),
    ticker_window: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    settings = get_settings(db)
    settings.ticker_speed_seconds = max(5, ticker_speed_seconds)
    settings.ticker_window = max(1, ticker_window)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=" + quote("Ticker settings saved"), status_code=303)


@router.post("/auction-dates", response_class=HTMLResponse)
def update_auction_dates(
    auction_date: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    settings = get_settings(db)
    try:
        settings.captain_auction_at = datetime.strptime(auction_date, "%Y-%m-%dT%H:%M")
    except ValueError:
        return RedirectResponse(url="/admin/settings?msg=" + quote("Invalid date/time"), status_code=303)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=" + quote("Auction date saved (IST)"), status_code=303)


@router.post("/timeout", response_class=HTMLResponse)
def update_timeout(
    timeout_seconds: int = Form(...),
    max_timeouts_per_team: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    settings = get_settings(db)
    settings.timeout_seconds = max(5, timeout_seconds)
    settings.max_timeouts_per_team = max(0, max_timeouts_per_team)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=" + quote("Timeout settings saved"), status_code=303)


@router.post("/theme", response_class=HTMLResponse)
def update_theme(
    theme: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    from app.templating import VALID_THEMES
    if theme not in VALID_THEMES:
        theme = "dark"
    settings = get_settings(db)
    settings.theme = theme
    settings.light_theme = (theme == "light")  # keep legacy column in sync
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=" + quote("Theme updated"), status_code=303)


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


@router.post("/reset-since", response_class=HTMLResponse)
def reset_since_time(
    cutoff: str = Form(...),
    confirm: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    if confirm != "RESET":
        return RedirectResponse(
            url="/admin/settings?msg=" + quote("Type RESET exactly to confirm, nothing was touched"),
            status_code=303,
        )
    try:
        cutoff_dt = datetime.strptime(cutoff, "%Y-%m-%dT%H:%M")
    except ValueError:
        return RedirectResponse(url="/admin/settings?msg=" + quote("Invalid date/time"), status_code=303)
    counts = reset_since(db, cutoff_dt)
    msg = (
        f"Reset since {cutoff_dt.strftime('%d %b %Y, %I:%M %p')} IST done. {counts['auctions']} auctions and "
        f"{counts['bids']} bids from after that time were undone (purses and team assignments reversed), "
        f"{counts['matches']} matches and {counts['playing_xi']} XI entries from after that time were cleared. "
        f"Everything on or before the cutoff was kept."
    )
    return RedirectResponse(url="/admin/settings?msg=" + quote(msg), status_code=303)


@router.post("/sounds", response_class=HTMLResponse)
def update_sounds(
    sound_bid: str = Form("classic"),
    sound_result: str = Form("classic"),
    sound_timer: str = Form("tick"),
    sound_roll: str = Form("whoosh"),
    db: Session = Depends(get_db),
    user: User = Depends(super_admin_only),
):
    settings = get_settings(db)
    settings.sound_bid = sound_bid if sound_bid in ("classic", "synth", "off") else "classic"
    settings.sound_result = sound_result if sound_result in ("classic", "synth", "off") else "classic"
    settings.sound_timer = sound_timer if sound_timer in ("tick", "beep", "off") else "tick"
    settings.sound_roll = sound_roll if sound_roll in ("whoosh", "chime", "off") else "whoosh"
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=" + quote("Sound settings saved"), status_code=303)
