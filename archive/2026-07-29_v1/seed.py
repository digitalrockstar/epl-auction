"""
Run once to create the first super admin.
    python seed.py
Then log in with the phone/password printed below.
"""
from app.database import SessionLocal, Base, engine
from app.models import User, Role
from app.auth import hash_password

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

db.close()
