"""
Wipes auction data only - bids, auctions, kit-image records, matches, and
playing-XI records - while leaving teams, managers, admins, super admins,
AND all player/user rows completely untouched.

On the Player table, only the fields that are a *result* of the auction get
reset: team_id, sold_price, is_captain. Everything else (name, phone,
registration details, CricHeroes stats, wants_captaincy, fee_status) stays
exactly as it was.

Use this to re-run an auction from scratch with the same registered players,
without having to re-import the registrations/stats CSVs.

    python reset_data.py

Safe to re-run - if a table's already empty, that step just does nothing.

Does NOT touch:
- Teams (name, colors, purse_total) - only purse_spent resets to 0 and
  captain_id clears.
- Manager/admin/super_admin login accounts.
- Player login accounts or their Player rows - only team_id, sold_price,
  and is_captain reset on each Player.
- Uploaded image files on disk (app/static/images/...).
"""
from app.database import SessionLocal
from app.models import Player, Team, PlayerTeamImage, Auction, Bid, Match, PlayingXI

db = SessionLocal()

print("Resetting auction data. Teams, managers, admins, and player/user records stay untouched.\n")

deleted = db.query(PlayingXI).delete(synchronize_session=False)
print(f"Deleted {deleted} playing XI record(s).")

deleted = db.query(Bid).delete(synchronize_session=False)
print(f"Deleted {deleted} bid(s).")

deleted = db.query(Auction).delete(synchronize_session=False)
print(f"Deleted {deleted} auction(s).")

deleted = db.query(PlayerTeamImage).delete(synchronize_session=False)
print(f"Deleted {deleted} kit-image record(s).")

deleted = db.query(Match).delete(synchronize_session=False)
print(f"Deleted {deleted} match(es).")

teams = db.query(Team).all()
for t in teams:
    t.captain_id = None
    t.purse_spent = 0
db.commit()
print(f"Cleared captain and reset purse_spent to 0 on {len(teams)} team(s).")

players = db.query(Player).all()
for p in players:
    p.team_id = None
    p.sold_price = None
    p.is_captain = False
db.commit()
print(f"Reset team/sold-price/captain flag on {len(players)} player(s). Player records themselves kept as-is.")

db.close()
print("\nDone. Players and all login accounts are untouched, ready for a fresh auction run.")
