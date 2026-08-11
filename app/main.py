import os
import logging
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import Base, engine, get_db
from app.models import User, Role, Team, Player, Bid, Auction, AuctionStatus
from app.auth import verify_password, get_current_user, normalize_phone, check_rate_limit, record_failed_login, clear_login_attempts
from app.routes.admin import router as admin_router
from app.routes.players import router as players_router, profile_router as players_profile_router
from app.routes.auction import router as auction_router
from app.routes.manager import router as manager_router
from app.routes.matches import router as matches_router
from app.routes.spectator import router as spectator_router
from app.routes.roll import router as roll_router
from app.routes.settings import router as settings_router

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="EPL Auction - Community Cricket")

SESSION_SECRET = os.getenv("SESSION_SECRET")
if not SESSION_SECRET:
    logger.warning(
        "SESSION_SECRET is not set, using an insecure default. "
        "Set it as an env var before going live, or logins won't survive a redeploy."
    )
    SESSION_SECRET = "dev-secret-change-me"

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
from app.templating import templates

# Creates tables on startup if they don't exist. Fine for this scale, swap for
# alembic migrations later if the schema needs to evolve without data loss.
Base.metadata.create_all(bind=engine)

app.include_router(admin_router)
app.include_router(players_router)
app.include_router(players_profile_router)
app.include_router(auction_router)
app.include_router(manager_router)
app.include_router(matches_router)
app.include_router(spectator_router)
app.include_router(roll_router)
app.include_router(settings_router)


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")

    ctx = {"request": request, "user": user}

    if user.role in (Role.super_admin, Role.admin):
        total_players = db.query(Player).count()
        sold = db.query(Player).filter(Player.team_id.isnot(None)).count()
        teams = db.query(Team).order_by(Team.id).all()
        total_purse = sum((t.purse_total or 0) for t in teams)
        spent_purse = sum((t.purse_spent or 0) for t in teams)
        recent_bids = db.query(Bid).order_by(Bid.created_at.desc()).limit(5).all()
        live = db.query(Auction).filter(Auction.status == AuctionStatus.live).first()
        ctx.update({
            "total_players": total_players,
            "sold": sold,
            "unsold": max(total_players - sold, 0),
            "teams": teams,
            "total_teams": len(teams),
            "total_purse": total_purse,
            "spent_purse": spent_purse,
            "remaining_purse": total_purse - spent_purse,
            "recent_bids": recent_bids,
            "live": live,
        })

    return templates.TemplateResponse("dashboard.html", ctx)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login_submit(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    norm = normalize_phone(phone)
    locked = check_rate_limit(norm)
    if locked:
        return templates.TemplateResponse("login.html", {"request": request, "error": locked})

    user = db.query(User).filter(User.phone == norm).first()
    if not user or not verify_password(password, user.password_hash):
        record_failed_login(norm)
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Wrong phone number or password"}
        )
    clear_login_attempts(norm)
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")
