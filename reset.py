"""
Same as seed.py but skips sample players: creates the super admin, 4 teams
and their managers only. Use this to set up real season data from scratch
without demo player clutter.

    python reset.py

Safe to re-run, only creates data that doesnt already exist.
"""
from app.database import SessionLocal, Base, engine
from app.models import User, Role, Team
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
    ("Yoddhas", "Manish KS", "9800044444", "444"),
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

db.close()
print("\nDone. Super admin, teams and managers created. No sample players.")
