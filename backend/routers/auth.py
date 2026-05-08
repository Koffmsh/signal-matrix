"""
auth.py — Schwab OAuth + JWT cookie auth.

Two routers exported:
  schwab_router  — Schwab OAuth (prefix /api/auth/schwab)
  router         — JWT cookie auth (prefix /api/auth)

Schwab OAuth endpoints (preserved exactly as before):
  GET    /api/auth/schwab/login     → redirect browser to Schwab auth page
  GET    /api/auth/schwab/callback  → receive code, exchange tokens, redirect home
  GET    /api/auth/schwab/status    → token status for SCHWAB header indicator
  DELETE /api/auth/schwab/logout    → clear tokens from Supabase

JWT cookie auth endpoints (new):
  POST /api/auth/register
  POST /api/auth/login
  POST /api/auth/logout
  GET  /api/auth/check
  POST /api/auth/forgot-password
  POST /api/auth/reset-password
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
import services.schwab_client as schwab_client
from services.auth_service import (
    hash_password,
    verify_password,
    validate_password_strength,
    create_jwt,
    get_user_from_token,
    create_reset_token,
    consume_reset_token,
    COOKIE_NAME,
    JWT_EXPIRY_HRS,
    IS_PRODUCTION,
)
from services.email_alert import (
    send_new_user_notification,
    send_duplicate_registration_notice,
    send_password_reset_email,
)

logger = logging.getLogger(__name__)


# ── Schwab OAuth router (existing, renamed from `router` to `schwab_router`) ──
schwab_router = APIRouter(prefix="/api/auth/schwab", tags=["schwab-auth"])


@schwab_router.get("/login")
def schwab_login():
    """Redirect the browser to the Schwab OAuth authorization page."""
    return RedirectResponse(url=schwab_client.get_auth_url())


@schwab_router.get("/callback")
def schwab_callback(code: str, db: Session = Depends(get_db)):
    """
    Receive authorization code from Schwab, exchange for tokens,
    store encrypted in Supabase, redirect to the production dashboard.
    """
    try:
        schwab_client.exchange_code_for_tokens(code, db)
    except Exception as e:
        logger.error(f"Schwab token exchange failed: {e}")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {e}")
    return RedirectResponse(url="https://signal.suttonmc.com")


@schwab_router.get("/status")
def schwab_status(db: Session = Depends(get_db)):
    """
    Return token status for the SCHWAB header indicator.
    Response: { connected, state: 'connected'|'aging'|'expired'|'disconnected', age_days? }
    """
    return schwab_client.get_status(db)


@schwab_router.delete("/logout")
def schwab_logout(db: Session = Depends(get_db)):
    """Clear all stored Schwab tokens. Requires re-authentication."""
    schwab_client.clear_tokens(db)
    return {"status": "logged_out"}


# ── JWT cookie auth router (new) ─────────────────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

GENERIC_LOGIN_ERROR = "Invalid email or password, or account not active"


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str | None = None
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/register")
@limiter.limit("3/hour")
async def register(req: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    REGISTER_SUCCESS = {
        "ok": True,
        "message": "Registration successful. Your account is pending approval.",
    }

    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        try:
            send_duplicate_registration_notice(req.email)
        except Exception as e:
            logger.warning(f"Duplicate registration email failed: {e}")
        return REGISTER_SUCCESS

    err = validate_password_strength(req.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    user = User(
        email=req.email,
        display_name=req.display_name,
        hashed_password=hash_password(req.password),
        role="viewer",
        status="pending",
    )
    db.add(user)
    db.commit()

    try:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        send_new_user_notification(req.email, req.display_name, ip, ua)
    except Exception as e:
        logger.warning(f"Registration email failed: {e}")

    return REGISTER_SUCCESS


@router.post("/login")
@limiter.limit("5/5minutes")
async def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    if user.status != "active":
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    token = create_jwt(str(user.id), user.role)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        max_age=JWT_EXPIRY_HRS * 3600,
        path="/",
    )

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    return {
        "ok": True,
        "role": user.role,
        "display_name": user.display_name,
        "email": user.email,
    }


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie. JWT remains valid until expiry —
    see 'Deferred decisions' in spec. Disable user in admin if true revocation needed."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/check")
async def check_session(request: Request, db: Session = Depends(get_db)):
    """Frontend calls this on mount to determine session validity.
    Always returns 200 — never 401 — so the apiFetch redirect logic doesn't loop."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return {"authenticated": False}
    user = get_user_from_token(token, db)
    if not user or user.status != "active":
        return {"authenticated": False}
    return {
        "authenticated": True,
        "role": user.role,
        "display_name": user.display_name,
        "email": user.email,
    }


@router.post("/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(req: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Always returns 200 — never reveal whether the email exists."""
    user = db.query(User).filter(User.email == req.email).first()
    if user and user.status == "active":
        try:
            token = create_reset_token(user, db)
            send_password_reset_email(user.email, token)
        except Exception as e:
            logger.warning(f"Password reset email failed: {e}")
    return {"ok": True, "message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password")
@limiter.limit("5/hour")
async def reset_password(req: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    err = validate_password_strength(req.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    user = consume_reset_token(req.token, db)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(req.new_password)
    db.commit()
    return {"ok": True, "message": "Password updated. Please log in."}
