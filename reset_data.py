"""
Wipes auction data only - bids, auctions, kit-image records, matches, and
playing-XI records - while leaving teams, managers, admins, super admins,
AND all player/user rows completely untouched.

On the Player table, only the fields that are a *result* of the auction get
reset: team_id, sold_price, is_captain. Everything else (name, phone,
registration details, CricHeroes stats, wants_captaincy, fee_status) stays
exactly as it was.

Use this to re-run an auction from scratch with the same registered players,
without having to re-import the registrations/stats CSVs. Same logic is
also available from Settings > Reset all data in the admin panel.

    python reset_data.py

Safe to re-run - if a table's already empty, that step just does nothing.
"""
from app.database import SessionLocal
from app.reset_logic import reset_auction_data

db = SessionLocal()
print("Resetting auction data. Teams, managers, admins, and player/user records stay untouched.\n")
counts = reset_auction_data(db)
print(f"Deleted {counts['playing_xi']} playing XI record(s).")
print(f"Deleted {counts['bids']} bid(s).")
print(f"Deleted {counts['auctions']} auction(s).")
print(f"Deleted {counts['kit_images']} kit-image record(s).")
print(f"Deleted {counts['matches']} match(es).")
print(f"Cleared captain and reset purse_spent to 0 on {counts['teams_reset']} team(s).")
print(
    f"Reset team/sold-price/captain flag on {counts['players_reset']} player(s). "
    "Player records themselves kept as-is."
)
db.close()
print("\nDone. Players and all login accounts are untouched, ready for a fresh auction run.")
