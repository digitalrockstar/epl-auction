from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.database import get_db
from app.models import User, Role

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
