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
- Team and manager setup, team branding (logo, primary/secondary color)
- Player registration import from forms.app CSV export
- CricHeroes stats import, matched by WhatsApp number (shows "New Player"/"No history found" if blank, never zeros)
- Player photos and team logos resolved automatically from a folder convention (see "Images" below), with an in-app upload button for one-off corrections
- Captain's auction (base 2L) and Player's auction (base 50k), same purse pool
- Slab-based bid increments (10k/20k/40k/50k), configurable in `app/config.py`
- Purse reserve rule: blocks bids that would leave a team unable to afford its minimum squad
- 180s auto-timer per player, resets on each bid, auto-resolves (sold to leader / unsold) on expiry
- Undo last bid
- Manager "My Team" view + one-click live bid panel (auto-disables when not applicable)
- Player profile pages (phone hidden from non-staff)
- Public spectator link at `/spectator/live`, no login, no PII
- Live TV screen with countdown timer, purse ticker, team colors, sound hooks, animations
- Telegram notifications on sold/unsold (set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, no-op if unset)
- Match scheduling, results, points table, Playing XI / min-2-games tracker
- Audit log of every bid
- Login rate limiting (5 attempts, 5 min lockout)
- `/healthz` for uptime checks

## Images (player photos, kit photos, team logos)
No need to upload anything one at a time, or paste URLs (Google Drive share links don't work here -
they don't serve raw image bytes, that's why pasted Drive links showed nothing). Just drop files into
these folders, named by phone number or team name, and the app finds them on its own:

```
app/static/images/players/main/<phone>.png          -> player's default photo
app/static/images/players/<team-slug>/<phone>.png   -> photo in that team's kit, shown once sold
app/static/images/teams/<team-slug>.png              -> team logo
```

- `<phone>` = the player's registered phone number, digits only, no `+91`, no spaces or dashes
  (e.g. `9876543210.png`).
- `<team-slug>` = team name, lowercased, spaces stripped (e.g. "Spartans" -> `spartans`,
  "Warriors XI" -> `warriorsxi`). If you rename a team, rename its folder/file to match.
- `.png` is checked first, `.jpg`/`.jpeg` also work.
- Folders for the 4 sample teams already exist: `spartans/`, `titans/`, `warriors/`, `yoddhas/`.
  Add more as you add teams.
- If a file isn't found, it falls back to the built-in placeholder silhouette/shield, never a broken image.
- The in-app "Photo" / "Kit" / "Upload logo" buttons on the Players and Teams pages do the exact same
  thing, they save straight into these folders. Use them for one-off corrections; use the folder drop
  for loading everyone at once.
- `CAPTAIN_BASE_PRICE` (200000), `PLAYER_BASE_PRICE` (50000)
- `MIN_SQUAD_SIZE` (13), `MAX_PURSE` (2500000), `TIMER_SECONDS` (180)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional)

## Not yet built
- Sound files aren't included, drop `bid.mp3`/`sold.mp3`/`unsold.mp3` into `app/static/sfx/`

## Deploying free
1. Push this to GitHub (already done if you're reading this on the repo).
2. Create a free Postgres DB on Neon.tech, copy the connection string.
3. Create a free web service on Render.com, point it at the repo.
4. Set env vars on Render: `DATABASE_URL` (from Neon), `SESSION_SECRET` (any random string, see `.env.example`).
5. Start command is already in `Procfile`: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Free tier sleeps after inactivity, first load after idle takes ~30s. Open the TV screen a minute before you need it.
7. After first deploy, run `python seed.py` once via Render's shell tab to create the super admin.

