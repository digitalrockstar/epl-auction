"""
Run once to create the first super admin, plus sample demo data
(4 teams, managers, a handful of players — some with CricHeroes stats,
some blank so the "New Player" state can be seen).

    python seed.py

Then log in with the phone/password printed below.
This file only creates data that doesn't already exist, safe to re-run.
Replace the sample teams/players below with real ones before going live.
"""
from app.database import SessionLocal, Base, engine
from app.models import User, Role, Team, Player
from app.auth import hash_password
from app.config import MAX_PURSE

Base.metadata.create_all(bind=engine)
db = SessionLocal()

PHONE = "9999999999"
PASSWORD = "changeme123"

existing = db.query(User).filter(User.phone == PHONE).first()
if existing:
    print(f"Super admin already exists: {PHONE}")
else:
    admin = User(
        name="Super Admin",
        phone=PHONE,
        password_hash=hash_password(PASSWORD),
        role=Role.super_admin,
    )
    db.add(admin)
    db.commit()
    print(f"Created super admin. Phone: {PHONE}  Password: {PASSWORD}")
    print("Change this password once you're in.")

# ---- Sample teams (replace with real team names/colors before going live) ----
SAMPLE_TEAMS = [
    {"name": "Spartans", "primary_color": "#7e5726", "secondary_color": "#95341b"},
    {"name": "Titans", "primary_color": "#a6b9bb", "secondary_color": "#0c1f2c"},
    {"name": "Warriors", "primary_color": "#8e1f1a", "secondary_color": "#c4932e"},
    {"name": "Yoddhas", "primary_color": "#bd7622", "secondary_color": "#0d486c"},
]
if db.query(Team).count() == 0:
    for t in SAMPLE_TEAMS:
        db.add(Team(name=t["name"], purse_total=MAX_PURSE, primary_color=t["primary_color"],
                     secondary_color=t["secondary_color"], logo_url="/static/img/placeholder_team_logo.svg"))
    db.commit()
    print(f"Created {len(SAMPLE_TEAMS)} sample teams with purse {MAX_PURSE}.")
else:
    print("Teams already exist, skipping sample teams.")

# ---- Sample managers, one per team (placeholder phones - swap for real numbers before going live) ----
MANAGERS = [
    ("Spartans", "Adarsh S", "9800011111", "111"),
    ("Titans", "Pavan T", "9800022222", "222"),
    ("Warriors", "Hitesh P", "9800033333", "333"),
    ("Yoddhas", "Himanshu R", "9800044444", "444"),
]
for team_name, mgr_name, phone, password in MANAGERS:
    team = db.query(Team).filter(Team.name == team_name).first()
    if not team:
        print(f"Skipped {mgr_name}: team '{team_name}' doesn't exist yet.")
        continue
    if team.manager_id:
        print(f"Skipped {mgr_name}: {team_name} already has a manager.")
        continue
    if db.query(User).filter(User.phone == phone).first():
        print(f"Skipped {mgr_name}: phone {phone} is already registered to someone else.")
        continue

    mgr = User(name=mgr_name, phone=phone, password_hash=hash_password(password), role=Role.manager)
    db.add(mgr)
    db.flush()  # need mgr.id before we can point team.manager_id at it
    team.manager_id = mgr.id
    print(f"Created manager for {team_name}. Phone: {phone}  Password: {password}")
db.commit()

# ---- Sample players (mix of stats-available and brand-new / blank) ----
SAMPLE_PLAYERS = [
    dict(name="Rohan Sharma", phone="9800000001", primary_skill="BAT - Batsman", batting_hand="Right Hand",
         bowling_style="Right Arm Off Break", wants_captaincy=True, experience_level="5+ Years",
         brief="Middle order batsman, good fielder, can bowl medium pace if needed.",
         bat_matches=42, bat_runs=1126, bat_avg=32.17, bat_sr=136.72, bowl_wickets=28, bowl_economy=7.25),
    dict(name="Arjun Verma", phone="9800000002", primary_skill="AR - All Rounder", batting_hand="Right Hand",
         bowling_style="Right Arm Medium", wants_captaincy=True, experience_level="5+ Years",
         bat_matches=38, bat_runs=740, bat_avg=24.6, bat_sr=118.4, bowl_wickets=19, bowl_economy=6.8),
    dict(name="Vikram Singh", phone="9800000003", primary_skill="BAT - Batsman", batting_hand="Right Hand",
         wants_captaincy=True, experience_level="5+ Years",
         bat_matches=50, bat_runs=1420, bat_avg=35.5, bat_sr=142.1),
    dict(name="Daniel Paul", phone="9800000004", primary_skill="WK - Wicketkeeper Batsman",
         batting_hand="Left Hand", is_wicketkeeper=True, wants_captaincy=True, experience_level="3-5 Years",
         bat_matches=30, bat_runs=560, bat_avg=22.4, bat_sr=110.0),
    dict(name="Sahil Mehta", phone="9800000005", primary_skill="BOWL - Bowler", batting_hand="Right Hand",
         bowling_style="Right Arm Fast", experience_level="3-5 Years",
         bowl_matches=35, bowl_wickets=41, bowl_economy=6.4),
    dict(name="Karan Desai", phone="9800000006", primary_skill="AR - All Rounder", batting_hand="Right Hand",
         bowling_style="Right Arm Medium", experience_level="1-3 Years"),
    dict(name="Amit Yadav", phone="9800000007", primary_skill="BOWL - Bowler", batting_hand="Left Hand",
         bowling_style="Left Arm Spin", experience_level="1-3 Years"),
    dict(name="Joel Daniel", phone="9800000008", primary_skill="BAT - Batsman", batting_hand="Right Hand",
         experience_level="Beginner"),  # blank stats on purpose -> shows "New Player"
    dict(name="Nikhil Reddy", phone="9800000009", primary_skill="AR - All Rounder", batting_hand="Right Hand",
         bowling_style="Right Arm Off Break", experience_level="Beginner"),  # blank stats -> "New Player"
    dict(name="Pranav Joshi", phone="9800000010", primary_skill="WK - Wicketkeeper Batsman",
         batting_hand="Right Hand", is_wicketkeeper=True, experience_level="Beginner"),  # blank -> "New Player"
]
if db.query(Player).count() == 0:
    for sp in SAMPLE_PLAYERS:
        phone = sp.pop("phone")
        name = sp.pop("name")
        u = User(name=name, phone=phone, password_hash=hash_password(phone[-6:]), role=Role.player)
        db.add(u)
        db.flush()
        db.add(Player(user_id=u.id, fee_amount=1700, profile_photo_url="/static/img/placeholder_player_photo.svg", **sp))
    db.commit()
    print(f"Created {len(SAMPLE_PLAYERS)} sample players (fee ₹1700 each, some blank stats for 'New Player' state).")
else:
    print("Players already exist, skipping sample players.")

db.close()
