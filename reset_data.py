"""
Wipes all player and auction data - players, their login accounts, bids,
auctions, kit-image records, matches, and playing-XI records - while
leaving teams, managers, admins, and super admins untouched.

Use this to clear out sample/test data before loading real registrations,
or to reset for a fresh test run without losing your team/manager setup.

    python reset_data.py

Safe to re-run - if a table's already empty, that step just does nothing.

Does NOT touch:
- Teams (name, colors, purse_total) - only purse_spent resets to 0 and
  captain_id clears, since the captain was a player about to be deleted.
- Manager/admin/super_admin login accounts.
- Uploaded image files on disk (app/static/images/...) - if the sample
  players' photos are still in there, delete those folders' contents
  manually, this script only touches the database.
"""
from app.database import SessionLocal
from app.models import Player, User, Team, PlayerTeamImage, Auction, Bid, Match, PlayingXI

db = SessionLocal()

print("Resetting player/auction data. Teams, managers and admins stay untouched.\n")

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

player_user_ids = [p.user_id for p in db.query(Player).all()]
deleted = db.query(Player).delete(synchronize_session=False)
print(f"Deleted {deleted} player profile(s).")

deleted = db.query(User).filter(User.id.in_(player_user_ids)).delete(synchronize_session=False)
print(f"Deleted {deleted} player login account(s).")

db.commit()
db.close()
print("\nDone. Teams, managers and admin accounts are untouched.")
print("Load real players via the Players page CSV import, or re-run seed.py's sample-player block for testing.")
