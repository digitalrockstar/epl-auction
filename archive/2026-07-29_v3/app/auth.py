from datetime import datetime, timedelta
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.database import get_db
from app.models import User, Role

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_LOGIN_ATTEMPTS: dict[str, list] = {}  # phone -> [count, locked_until]
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 5


def check_rate_limit(phone: str) -> str | None:
    entry = _LOGIN_ATTEMPTS.get(phone)
    if entry and entry[1] and datetime.utcnow() < entry[1]:
        return f"Too many attempts, try again in a few minutes"
    return None


def record_failed_login(phone: str):
    entry = _LOGIN_ATTEMPTS.setdefault(phone, [0, None])
    entry[0] += 1
    if entry[0] >= MAX_ATTEMPTS:
        entry[1] = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)


def clear_login_attempts(phone: str):
    _LOGIN_ATTEMPTS.pop(phone, None)


def normalize_phone(raw: str) -> str:
    """Strips spaces, dashes, +91 country code, so numbers pasted in different
    formats from WhatsApp/forms.app still match the same stored user."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[-10:]
    return digits


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Pulls the logged-in user from the session cookie. Returns None if nobody's logged in,
    routes decide for themselves whether that's allowed."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_role(*allowed_roles: Role):
    """Use as a dependency: Depends(require_role(Role.super_admin, Role.admin))"""
    def checker(request: Request, db: Session = Depends(get_db)) -> User:
        user = require_login(request, db)
        if user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
        return user
    return checker
