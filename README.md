# Community Cricket Auction App

Season 3, IPL-style auction, built for free hosting.

## Stack
FastAPI + Jinja2 + htmx + SQLAlchemy. Postgres in production (Neon/Supabase free tier), sqlite locally.

## Run it locally

```
pip install -r requirements.txt
python seed.py          # creates the first super admin
uvicorn app.main:app --reload
```

Visit http://localhost:8000/login and use the phone/password seed.py prints.

## What's built so far (Step 1)
- Project structure
- Full data model: User, Team, Player, Auction, Bid, Match, PlayingXI
- Session-based login with role support (super_admin, admin, manager, captain, player)
- Base layout with htmx wired in

## Not built yet
- Team and manager setup screens
- Player registration flow
- Captain's auction
- Player's auction
- Match scheduling and Playing XI tracker

## Deploying free
1. Push this to GitHub.
2. Create a free Postgres DB on Neon.tech, copy the connection string.
3. Create a free web service on Render.com, point it at the repo.
4. Set env vars on Render: `DATABASE_URL` (from Neon), `SESSION_SECRET` (any random string).
5. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
