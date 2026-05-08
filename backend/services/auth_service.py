"""
auth_service.py — JWT cookie auth, password hashing, password-reset tokens.

See Docs/Auth_User_Management_Spec_v1.0.md for full context.
"""

import bcrypt
import jwt
import secrets
import re
import os
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from models.user import User
from models.password_reset_token import PasswordResetToken

logger = logging.getLogger(__name__)

JWT_SECRET      = os.getenv("JWT_SECRET")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRY_HRS  = 12
COOKIE_NAME     = "sm_session"
RESET_TOKEN_TTL = 15  # minutes
IS_PRODUCTION   = os.getenv("ENVIRONMENT", "development") == "production"

# Common password blocklist — small list, rejects the obvious
COMMON_PASSWORDS = {
    "password", "password1", "password123", "admin", "admin123",
    "12345678", "qwerty12", "letmein", "welcome", "abc12345",
    "qwertyuiop", "1q2w3e4r", "iloveyou", "monkey", "dragon",
    "sunshine", "princess", "football", "baseball", "shadow",
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def validate_password_strength(password: str) -> str | None:
    """Returns error message if invalid, None if valid."""
    if len(password) < 12:
        return "Password must be at least 12 characters"
    if password.lower() in COMMON_PASSWORDS:
        return "Password is too common — please choose a different one"
    if not re.search(r"[a-zA-Z]", password):
        return "Password must contain at least one letter"
    if not re.search(r"\d", password) and len(password) < 16:
        return "Password must contain at least one number, or be 16+ characters"
    return None


def create_jwt(user_id: str, role: str) -> str:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HRS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    if not JWT_SECRET:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_user_from_token(token: str, db: Session) -> User | None:
    """Decodes JWT, returns user from DB or None."""
    payload = decode_jwt(token)
    if not payload:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    return db.query(User).filter(User.id == sub).first()


def create_reset_token(user: User, db: Session) -> str:
    # Invalidate any existing unused tokens for this user
    db.query(PasswordResetToken)\
      .filter(PasswordResetToken.user_id == user.id, PasswordResetToken.used == False)\
      .update({"used": True})

    token = secrets.token_urlsafe(32)
    reset = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL),
    )
    db.add(reset)
    db.commit()
    return token


def consume_reset_token(token: str, db: Session) -> User | None:
    """Returns the user if token is valid and unexpired. Marks token used."""
    record = db.query(PasswordResetToken)\
               .filter(PasswordResetToken.token == token,
                       PasswordResetToken.used == False)\
               .first()
    if not record:
        return None
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    user = db.query(User).filter(User.id == record.user_id).first()
    record.used = True
    db.commit()
    return user


def require_admin_user(request, db: Session):
    """FastAPI dependency factory. Re-fetches user from DB and validates LIVE
    role — never trusts the JWT role payload (which can be stale up to 12h).
    Raises 403 on any failure. Used by admin-only endpoints across routers."""
    from fastapi import HTTPException
    token = request.cookies.get(COOKIE_NAME)
    user = get_user_from_token(token, db) if token else None
    if not user or user.status != "active" or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user


def seed_admin_if_empty(db: Session) -> None:
    """Called on FastAPI startup. Creates admin account if users table is empty.
    Idempotent — safe to call on every startup."""
    if db.query(User).count() > 0:
        return
    admin_email    = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    admin_name     = os.getenv("ADMIN_DISPLAY_NAME", "Admin")
    if not admin_email or not admin_password:
        logger.warning("ADMIN_EMAIL or ADMIN_PASSWORD not set — no seed admin created")
        return
    admin = User(
        email=admin_email,
        display_name=admin_name,
        hashed_password=hash_password(admin_password),
        role="admin",
        status="active",
    )
    db.add(admin)
    db.commit()
    logger.info(f"Seed admin created: {admin_email}")
