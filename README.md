# Community Cricket Auction App

Season 3, IPL-style auction, built for free hosting.

## Versioning
Old code lives in `archive/`, dated by folder. Never overwritten or deleted, only replaced at root. Current live code is always at repo root.

## Stack
FastAPI + Jinja2 + htmx + SQLAlchemy. Postgres in production (Neon/Supabase free tier), sqlite locally.

## Run it locally

```
pip install -r requirements.txt
python seed.py          # creates the first super admin
uvicorn app.main:app --reload
```

Visit http://localhost:8000/login and use the phone/password seed.py prints.

## What's built
- Team and manager setup (super admin)
- Player registration import from forms.app CSV export
- CricHeroes stats import, matched by WhatsApp number
- Per-team kit image assignment per player
- Captain's auction and Player's auction, admin-controlled bidding
- Live TV display at `/auction/live`, auto-refreshes every 3s
- Purse tracking, bid floor validation, re-auction of unsold players
- `/healthz` for uptime checks

## Not built yet
- Match scheduling and Playing XI / min-2-games tracker
- Points table

## Deploying free
1. Push this to GitHub (already done if you're reading this on the repo).
2. Create a free Postgres DB on Neon.tech, copy the connection string.
3. Create a free web service on Render.com, point it at the repo.
4. Set env vars on Render: `DATABASE_URL` (from Neon), `SESSION_SECRET` (any random string, see `.env.example`).
5. Start command is already in `Procfile`: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Free tier sleeps after inactivity, first load after idle takes ~30s. Open the TV screen a minute before you need it.
7. After first deploy, run `python seed.py` once via Render's shell tab to create the super admin.

