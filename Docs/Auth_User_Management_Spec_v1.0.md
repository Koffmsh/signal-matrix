# Signal Matrix — Auth & User Management Spec v1.0

**Full-stack security layer — Neo implementation brief**

> **READ FIRST:** Read `CLAUDE.md` in full before starting. Do not begin implementation until you have read this document end to end. This spec supersedes all prior Tier 3 security drafts. Do not implement static API keys.

---

## Overview

This spec replaces the existing `REACT_APP_ADMIN_PASSWORD` client-side gate with a complete server-validated authentication and user management layer. The architecture is JWT-in-httpOnly-cookie, role-based access (Admin / Viewer), self-registration with admin approval, and an admin Users tab inside `/admin`.

**What this spec adds**

1. JWT httpOnly cookie session, 12-hour expiry, all routes protected
2. `users` and `password_reset_tokens` tables in Supabase
3. Self-registration → pending state → admin approval → activation
4. Password reset flow via email link (15-minute token TTL)
5. Email notifications to Shannon on new registration (with IP + user-agent + timestamp)
6. Admin Users tab in AdminPanel for user CRUD
7. Seeded admin account from Fly.io secrets on first startup
8. App-level rate limiting (slowapi) on auth endpoints
9. Recovery runbook (`Docs/RUNBOOK_AUTH_RECOVERY.md`) and CLI reset script (`backend/scripts/reset_admin.py`)

**What this spec removes**

- `REACT_APP_ADMIN_PASSWORD` (no longer used anywhere — full deletion)
- The client-side admin password gate in `AdminPanel.js`

---

## Deferred decisions — considered and rejected for v1.0

These were evaluated during spec drafting and intentionally NOT included. Documenting here so future reviewers understand the trade-offs and know when to revisit.

### Token blocklist for real logout invalidation

**Status:** Deferred.

**What it would have done:** Add a `token_blocklist` table that stores invalidated JWT IDs. On logout, the JWT's `jti` (JWT ID) is recorded in the blocklist. Middleware checks the blocklist on every request — if the JTI is present, the JWT is rejected even though it's cryptographically valid and unexpired.

**Why deferred:** For the current threat model (single primary user, possibly 1–2 trusted viewers, no PII, no order execution capability), the blocklist solves a marginal problem at meaningful cost. The realistic "stolen JWT" attack scenarios (lost phone, captured network traffic) are already mitigated by `Disable user` in admin — the middleware checks `user.status != "active"` on every request and returns 401 for disabled accounts. The blocklist's only unique value is making the logout button do something cryptographically meaningful, which is theoretical reassurance for a tool used on trusted devices.

**Cost rejected:** new table, daily cleanup cron job, ~30 lines of code, one more failure surface. Without the blocklist, logout = clear cookie client-side; the JWT itself remains valid until natural expiry (12h max) but is unreachable to the legitimate session.

**Revisit when:**
- Multiple users actively share devices (e.g., a partner workstation)
- Adding mobile clients where lost-phone risk increases
- Customer/client portal use cases (untrusted devices)
- Compliance requirement explicitly requires session revocation on logout

### `useApiFetch` hook with React Router soft navigation

**Status:** Deferred.

**What it would have done:** Replace the static `apiFetch` function with a `useApiFetch` hook that uses `useNavigate` from React Router. On 401, soft-navigate to `/login` (preserves React state, scroll position, in-progress UI state). The current spec uses `window.location.href = '/login'` — a hard navigation that triggers a full page reload.

**Why deferred:** Session expiry triggers at most every 12 hours. For a market data dashboard, "lose scroll position and filter state once per day" is barely perceptible; the user re-derives state from fresh server data anyway. The hook approach has real costs: every component that calls `apiFetch` must wire the hook through component bodies, and `useApiFetch` calls outside a `<BrowserRouter>` context crash. The static function is callable from anywhere with no plumbing.

**Cost rejected:** ~15 lines of plumbing per consumer file, hook-context bug surface, refactoring impact across `App.js`, `AdminPanel.js`, `TickerList.js`, `QuadSetup.js`, `UserList.js`.

**Revisit when:**
- Adding rich client-side state that's expensive to recreate (long forms, draft entries, complex filter UI that the user wouldn't want to lose)
- Multi-step workflows where mid-flow interruption is jarring
- User feedback indicates session-expiry redirects are disruptive

### Cloudflare WAF rate limiting on auth endpoints

**Status:** Documented as Option 2 (future enhancement). Not implemented in v1.0 deploy.

**What it would have done:** Cloudflare-edge rate limiting on `/api/auth/login` (5/5min per IP), `/api/auth/forgot-password` (3/hour), `/api/auth/register` (3/hour). Brute-force and registration-spam protection at the network edge before requests ever reach the API.

**Why deferred:** Cloudflare WAF rate limiting requires `api.signal.suttonmc.com` to be Proxied (orange cloud). Currently DNS-only because proxying api.signal breaks the Schwab OAuth callback (per CLAUDE.md). Switching to Proxied requires also adding a Cloudflare Configuration Rule to bypass interventions on `/api/auth/schwab/callback`, then verifying Schwab OAuth still works post-proxy. That's a separate infra change with real regression risk on a system that's relied on every morning — bundling it into the auth migration is poor risk management.

**What ships instead:** `slowapi` at the FastAPI app level provides equivalent rate limits for the single-machine Fly.io deployment. Login: 5/5min. Forgot-password: 3/hour. Register: 3/hour.

**Revisit when:**
- Scaling to multiple Fly.io machines (slowapi is per-process; rate limits don't sync)
- Observed brute-force attempts in logs
- Any architectural change that already requires touching api.signal proxy status

---

## Architecture decisions and rationale

These are decisions where the obvious choice is wrong; documenting the why so future-Neo doesn't "fix" them.

### Cookie config: `samesite="lax"`, not `"strict"`

`samesite="strict"` breaks links from email clients (password reset link in an email is a cross-site navigation; the cookie won't be sent). `samesite="lax"` blocks the dangerous CSRF cases (cross-site POSTs) while allowing top-level navigations. Standard choice for session cookies.

### Cookie config: `secure` is environment-dependent

`secure=True` requires HTTPS. Local dev runs on `http://localhost:3000`. Hardcoding `secure=True` causes silent login failures locally. Read from `ENVIRONMENT` env var.

### `/docs`, `/openapi.json`, `/redoc` disabled in production

Exposes full API schema to anyone on the internet — major recon gift to attackers. Disabled via `docs_url=None` in production; available locally.

### JWT role check uses live DB value, not JWT payload

JWT payload includes role at issue time. If admin is demoted to viewer, the stale JWT keeps admin access until expiry (up to 12 hours). The middleware already loads the user from DB; the role check uses that live value. JWT role is informational only.

### Generic 401 for all login failures

Distinguishing "invalid email" from "pending account" lets attackers enumerate registered emails. Every failure returns the same 401 with the same message. Trade-off: legit users with pending accounts get less helpful feedback. Acceptable because admin manually communicates approval.

### Direct password rules, not framework

Password complexity rules are inline (`validate_password_strength`) rather than via a library. Rationale: 30 lines of explicit code is more auditable than a dependency, and the rules follow NIST SP 800-63B (length over complexity, common-password blocklist).

### Static `apiFetch` with hard navigation on 401

See "Deferred decisions" above. Static function chosen over hook for simplicity and cross-context callability. Hard navigation accepted because session expiry is rare (≤ once per 12h) and the dashboard re-renders cleanly from server data on next load.

---

## Part 1 — Database schema

### `users` table

```python
# backend/models/user.py

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid
from datetime import datetime, timezone

class User(Base):
    __tablename__ = "users"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email           = Column(String, unique=True, nullable=False, index=True)
    display_name    = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    role            = Column(String, nullable=False, default="viewer")   # "admin" | "viewer"
    status          = Column(String, nullable=False, default="pending")  # "active" | "pending" | "disabled"
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login      = Column(DateTime(timezone=True), nullable=True)
```

### `password_reset_tokens` table

```python
# backend/models/password_reset_token.py

from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid
from datetime import datetime, timezone

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), nullable=False, index=True)
    token      = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used       = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

### Alembic migration notes

UUID handling: Postgres uses native UUID; SQLite stores as TEXT. `as_uuid=True` works in both via SQLAlchemy. No special handling needed.

Migrations to generate:
- `add_users_table`
- `add_password_reset_tokens_table`

---

## Part 2 — Dependencies

Add to `backend/requirements.txt` (verify each is not already present):

```
bcrypt==4.1.2
PyJWT==2.8.0
slowapi==0.1.9
email-validator>=2.0.0
```

`slowapi` provides app-level rate limiting on auth endpoints. `email-validator` is required by Pydantic's `EmailStr` type used throughout the auth router; without it, FastAPI raises `ImportError` on startup.

---

## Part 3 — Auth service

```python
# backend/services/auth_service.py

import bcrypt
import jwt
import secrets
import re
import os
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from models.user import User
from models.password_reset_token import PasswordResetToken

JWT_SECRET      = os.getenv("JWT_SECRET")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRY_HRS  = 12
COOKIE_NAME     = "sm_session"
RESET_TOKEN_TTL = 15   # minutes
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
    return bcrypt.checkpw(password.encode(), hashed.encode())


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
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HRS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict | None:
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
    return db.query(User).filter(User.id == payload["sub"]).first()


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
    if record.expires_at < datetime.now(timezone.utc):
        return None
    user = db.query(User).filter(User.id == record.user_id).first()
    record.used = True
    db.commit()
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
        print("WARNING: ADMIN_EMAIL or ADMIN_PASSWORD not set — no seed admin created")
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
    print(f"Seed admin created: {admin_email}")
```

---

## Part 4 — Email service additions

The email service already exists (separate from Twilio SMS). Add two new functions and one helper.

### Update `backend/services/email_alert.py`

The existing file is `email_alert.py` (not `email_service.py`). It uses `SMTP_SSL` on port 465.
It exposes one function: `send_email(subject, body)` which always sends to `_TO` (Shannon).
Add a parameterized variant that matches the existing SMTP setup exactly:

```python
# Add to backend/services/email_alert.py — do NOT change the existing send_email() function

def send_email_to(recipient: str, subject: str, body: str) -> bool:
    """Sends email to an arbitrary recipient. Used for password reset links.
    Matches send_email() SMTP setup exactly — SMTP_SSL port 465."""
    if not all([_FROM, _PASSWORD]):
        logger.warning("Email: credentials not configured — skipping send")
        return False

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = _FROM
        msg["To"]      = recipient

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(_FROM, _PASSWORD)
            smtp.sendmail(_FROM, recipient, msg.as_string())

        logger.info(f"Email sent to {recipient}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def send_new_user_notification(
    email: str,
    display_name: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Alerts Shannon when a genuinely new user registers."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et_now = datetime.now(ZoneInfo("America/New_York")).strftime("%m/%d/%y %H:%M ET")

    subject = f"Signal Matrix — New Registration: {display_name or email}"
    body = f"""
New user registration pending your approval.

Email:        {email}
Display name: {display_name or '(not provided)'}
Registered:   {et_now}
IP address:   {ip_address or 'unknown'}
User agent:   {user_agent or 'unknown'}

Approve or disable at:
https://signal.suttonmc.com/admin/users
""".strip()
    send_email(subject, body)   # to Shannon


def send_duplicate_registration_notice(email: str) -> None:
    """Sent to the registered address when someone tries to register with an already-taken email.
    Tells the owner without revealing to the requester that the email exists."""
    subject = "Signal Matrix — Registration Attempt"
    body = """
Someone tried to register a Signal Matrix account using your email address.

If that was you, you already have an account. You can log in or reset your password at:
https://signal.suttonmc.com/login

If this wasn't you, no action is needed — no changes were made to your account.
""".strip()
    send_email_to(email, subject, body)


def send_password_reset_email(email: str, reset_token: str) -> None:
    """Sends password reset link to the user."""
    reset_url = f"https://signal.suttonmc.com/reset-password?token={reset_token}"
    subject = "Signal Matrix — Password Reset"
    body = f"""
You requested a password reset for your Signal Matrix account.

Reset your password here (link expires in 15 minutes):
{reset_url}

If you did not request this, ignore this email — no changes will be made.
""".strip()
    send_email_to(email, subject, body)
```

---

## Part 5 — Auth router

**IMPORTANT — do NOT replace `backend/routers/auth.py`.** That file already contains the Schwab
OAuth endpoints (login, callback, status, logout) under `prefix="/api/auth/schwab"`. Those routes
must be preserved exactly as-is. Add the new JWT auth routes to the same file.

**Variable rename required:** the existing Schwab router is currently named `router`. The new JWT
auth router below is also named `router` — same Python variable name in the same module would
silently overwrite. Rename the existing one to `schwab_router` and update `main.py` accordingly:

```python
# auth.py — rename existing line
schwab_router = APIRouter(prefix="/api/auth/schwab", tags=["schwab-auth"])
# Update all @router.get / @router.delete decorators on Schwab endpoints to @schwab_router.

# main.py — change import + registration
from routers.auth import schwab_router, router as auth_router
app.include_router(schwab_router)
app.include_router(auth_router)
```

The combined file will have two routers: the existing `schwab_router` (Schwab OAuth) and the new
`router` (JWT auth). Register both in `main.py`.

```python
# backend/routers/auth.py — ADD to existing file, do not replace
# Keep all existing Schwab OAuth code (schwab_router) intact above this block.

from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from database import get_db
from models.user import User
from services.auth_service import (
    hash_password, verify_password, validate_password_strength,
    create_jwt, get_user_from_token,
    create_reset_token, consume_reset_token,
    COOKIE_NAME, JWT_EXPIRY_HRS, IS_PRODUCTION,
)
from services.email_alert import send_new_user_notification, send_duplicate_registration_notice, send_password_reset_email
from datetime import datetime, timezone

router = APIRouter(prefix="/api/auth")
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
    # Always return the same 200 response — never reveal whether the email exists.
    REGISTER_SUCCESS = {"ok": True, "message": "Registration successful. Your account is pending approval."}

    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        # Quietly email the registered address — screen message is identical to new registration.
        try:
            send_duplicate_registration_notice(req.email)
        except Exception as e:
            print(f"Duplicate registration email failed: {e}")
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

    # Notify Shannon — non-fatal if email fails
    try:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        send_new_user_notification(req.email, req.display_name, ip, ua)
    except Exception as e:
        print(f"Registration email failed: {e}")

    return REGISTER_SUCCESS


@router.post("/login")
@limiter.limit("5/5minutes")
async def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()

    # Single error path — never differentiate between not-found / bad-password / pending / disabled
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    if user.status != "active":
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    # Issue JWT cookie
    token = create_jwt(str(user.id), user.role)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=IS_PRODUCTION,        # HTTPS-only in production; permissive locally
        samesite="lax",              # allows email-link clickthrough; blocks CSRF POSTs
        max_age=JWT_EXPIRY_HRS * 3600,
        path="/",
    )

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    return {"ok": True, "role": user.role, "display_name": user.display_name, "email": user.email}


@router.post("/logout")
async def logout(response: Response):
    """Clears the session cookie. JWT remains valid until expiry —
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
            print(f"Password reset email failed: {e}")
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
```

### Register slowapi in `main.py`

```python
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from routers.auth import limiter as auth_limiter

app.state.limiter = auth_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

---

## Part 6 — Users admin router

```python
# backend/routers/users.py

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from services.auth_service import hash_password, validate_password_strength, get_user_from_token, COOKIE_NAME

router = APIRouter(prefix="/api/users")


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Re-fetches the user from DB and validates LIVE role — not stale JWT role."""
    token = request.cookies.get(COOKIE_NAME)
    user = get_user_from_token(token, db) if token else None
    if not user or user.status != "active" or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user


class UpdateUserRequest(BaseModel):
    status: str | None = None       # "active" | "pending" | "disabled"
    role: str | None = None         # "admin" | "viewer"
    display_name: str | None = None


class AdminResetPasswordRequest(BaseModel):
    new_password: str


@router.get("")
async def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role,
            "status": u.status,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    req: UpdateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Self-protection guards — admin cannot lock themselves out
    is_self = str(user.id) == str(admin.id)
    if is_self and req.status == "disabled":
        raise HTTPException(status_code=400, detail="Cannot disable your own account")
    if is_self and req.role == "viewer":
        raise HTTPException(status_code=400, detail="Cannot demote your own account from admin")

    if req.status is not None:
        user.status = req.status
    if req.role is not None:
        user.role = req.role
    if req.display_name is not None:
        user.display_name = req.display_name

    db.commit()
    return {"ok": True}


@router.post("/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str,
    req: AdminResetPasswordRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin sets a new password directly — no email flow. Used for forgot-password lockouts."""
    err = validate_password_strength(req.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = hash_password(req.new_password)
    db.commit()
    return {"ok": True}
```

---

## Part 7 — Middleware

```python
# Update backend/main.py

from fastapi import Request
from fastapi.responses import JSONResponse
from services.auth_service import get_user_from_token, COOKIE_NAME
from database import SessionLocal

# Paths accessible without authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/check",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/schwab/callback",   # Schwab OAuth — never gate
    "/api/auth/schwab/login",      # Initiates Schwab OAuth
}

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    db = SessionLocal()
    try:
        user = get_user_from_token(token, db)
    finally:
        db.close()

    if not user or user.status != "active":
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    request.state.user = user
    return await call_next(request)
```

### Disable docs in production

Update FastAPI app initialization:

```python
import os
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

app = FastAPI(
    lifespan=lifespan,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
```

### CORS — confirm `allow_credentials=True`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://signal.suttonmc.com",
        "http://localhost:3000",
    ],
    allow_credentials=True,        # CRITICAL — required for cookie cross-origin
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Part 8 — Startup hook

### Seed admin on first startup

```python
from services.auth_service import seed_admin_if_empty

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Existing startup code...
    db = SessionLocal()
    try:
        seed_admin_if_empty(db)
    finally:
        db.close()
    yield
    # Existing shutdown code...
```

---

## Part 9 — Frontend: AuthContext

```javascript
// src/context/AuthContext.js

import { createContext, useContext, useState, useEffect } from 'react';

const API_URL = process.env.REACT_APP_API_URL;

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    checkSession();
  }, []);

  // NOTE: this function uses raw fetch, NOT apiFetch.
  // /api/auth/check returns 200 with {authenticated: false} when not logged in,
  // so the apiFetch 401-redirect would never fire — but if we ever switch to 401,
  // using apiFetch here would cause an infinite redirect loop. Keep raw fetch here.
  const checkSession = async () => {
    try {
      const res = await fetch(`${API_URL}/api/auth/check`, {
        credentials: 'include',
      });
      const data = await res.json();
      setUser(data.authenticated ? data : null);
    } catch {
      setUser(null);
    } finally {
      setAuthLoading(false);
    }
  };

  const login = async (email, password) => {
    const res = await fetch(`${API_URL}/api/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (res.ok) {
      const data = await res.json();
      setUser({ email: data.email, role: data.role, display_name: data.display_name });
      return { ok: true };
    }
    const err = await res.json();
    return { ok: false, error: err.detail };
  };

  const logout = async () => {
    await fetch(`${API_URL}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, authLoading, login, logout, checkSession }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
```

Add `AuthProvider` inside `App.js` — keep `BrowserRouter` where it already is:

```javascript
// In App.js — wrap existing BrowserRouter content with AuthProvider
import { AuthProvider } from './context/AuthContext';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppLayout />   {/* existing content unchanged */}
      </AuthProvider>
    </BrowserRouter>
  );
}
```

`AuthProvider` does not use any React Router hooks internally, so it does not need to move to `index.js`. Keep `BrowserRouter` in `App.js` to minimise churn. Do NOT move `BrowserRouter` to `index.js`.

---

## Part 10 — Frontend: apiFetch (static function)

**IMPORTANT — do NOT replace `src/services/api.js`.** That file already contains
`fetchCachedMarketData()`, `fetchBatchMarketData()`, `fetchSpxVolHistory()`, and `fetchQuote()`,
which are used by the page-load and REFRESH DATA flows respectively. Replacing the file destroys
those functions and breaks the dashboard. Add `apiFetch` as a new export alongside the existing
functions. Note: callers will import via `'../services/api'` (or matching relative path), not
`'../utils/api'`.

**API_URL prefix:** `apiFetch` prepends `API_URL` internally. Callers pass just `/api/...`
— not `${API_URL}/api/...`. Every migration from the old `fetch(\`${API_URL}/api/...\`)`
pattern must strip the `${API_URL}` prefix. The existing `fetchCachedMarketData` and
`fetchBatchMarketData` already handle their own full URLs and do NOT need to be rewritten
to use `apiFetch` — leave them as-is.

```javascript
// ADD to existing src/services/api.js — do not replace the file

const API_URL = process.env.REACT_APP_API_URL;

/**
 * API fetch wrapper. Always sends the session cookie.
 * On 401 (session expired), hard-redirects to /login.
 *
 * Hard navigation is intentional — see 'Deferred decisions' in
 * Docs/Auth_User_Management_Spec_v1.0.md (rejected useApiFetch hook).
 *
 * Usage:
 *   import { apiFetch } from '../utils/api';
 *   const res = await apiFetch('/api/signals/stored');
 *   // NOTE: pass /api/... only — do NOT include ${API_URL} prefix
 *
 * DO NOT use this for /api/auth/check, /api/auth/login, /api/auth/logout —
 * those use raw fetch in AuthContext.
 */
export const apiFetch = async (path, options = {}) => {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (res.status === 401) {
    window.location.href = '/login';
    return null;
  }
  return res;
};
```

---

## Part 11 — Frontend: ProtectedRoute

```javascript
// src/components/shared/ProtectedRoute.js

import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

const ProtectedRoute = ({ children, requireAdmin = false }) => {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return (
      <div style={{ padding: '40px', color: '#8899aa', textAlign: 'center' }}>
        Loading...
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (requireAdmin && user.role !== 'admin') return <Navigate to="/" replace />;

  return children;
};

export default ProtectedRoute;
```

### Update App.js routes

```javascript
import ProtectedRoute from './components/shared/ProtectedRoute';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';

function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      {/* Protected — admin only */}
      <Route path="/admin/*" element={
        <ProtectedRoute requireAdmin>
          <AdminPanel />
        </ProtectedRoute>
      } />

      {/* Protected — any authenticated user (catch-all) */}
      <Route path="/*" element={
        <ProtectedRoute>
          <AppLayout />
        </ProtectedRoute>
      } />
    </Routes>
  );
}
```

---

## Part 12 — Frontend: Auth pages

All four pages match the existing dark theme: background `#0a0e1a`, panels `#0e1424`, borders `#1d2638`, primary green `#00e5a0`, error red `#ff4d6d`, body text `#c8d8e8`, secondary text `#8899aa`. Maximum 480px width centered.

### `src/pages/LoginPage.js`

- Fields: Email, Password
- Button: "Sign In"
- Links: "Forgot password?" → `/forgot-password`, "Don't have an account? Register" → `/register`
- On submit: call `useAuth().login(email, password)` → on success navigate to `/`; on failure show error from response
- Error message: show `error` from auth context (e.g., "Invalid email or password, or account not active")

### `src/pages/RegisterPage.js`

- Fields: Email, Display Name (optional), Password, Confirm Password
- Client-side validation: password ≥ 12 chars, passwords match
- Button: "Create Account"
- POST to `/api/auth/register` (raw fetch, no auth cookie required)
- Success state: full-width message "Your account is pending approval. You'll be notified when activated." with "Back to login" link
- Link: "Already have an account? Sign in" → `/login`

### `src/pages/ForgotPasswordPage.js`

- Field: Email only
- Button: "Send Reset Link"
- POST to `/api/auth/forgot-password` (raw fetch)
- Always shows success message regardless of API response (backend already enforces enumeration resistance)
- Link: "Back to login"

### `src/pages/ResetPasswordPage.js`

- Reads `?token=` from URL via `useSearchParams`
- Fields: New Password, Confirm Password
- Client-side validation: password ≥ 12 chars, passwords match
- Button: "Reset Password"
- POST to `/api/auth/reset-password` with `{token, new_password}`
- On success: show "Password updated. Redirecting..." → `setTimeout` 2s → navigate to `/login`
- On failure: show error message ("This reset link is invalid or has expired.")

---

## Part 13 — Frontend: Admin Users tab

### `src/components/Admin/UserList.js`

Table columns:

| Column | Notes |
|---|---|
| Email | |
| Display Name | "—" if null |
| Role | Dropdown: Admin / Viewer; PATCH on change |
| Status | Pending (amber badge) / Active (green badge) / Disabled (grey badge) |
| Last Login | ET formatted, "Never" if null |
| Registered | ET formatted date |
| Actions | Activate / Disable / Reset Password |

**Actions logic:**

- **Activate** — visible on rows where `status` is `pending` OR `disabled`. Click → PATCH `status="active"`. Single button handles both transitions.
- **Disable** — visible only on rows where `status === "active"`. Click → PATCH `status="disabled"`.
- **Reset Password** — visible on all rows. Opens modal: enter new password (validated client-side ≥ 12 chars) → POST to `/api/users/{id}/reset-password`.

**Self-protection in UI:**

The current admin's row should:
- Disable the role dropdown (prevent self-demotion)
- Hide the Disable button (prevent self-disable)
- Still allow Reset Password (legitimate use case)

The backend enforces these guards regardless, but disabling at the UI level gives clearer feedback than a 400 error.

### Add USERS tab to AdminPanel

```javascript
// In src/components/Admin/AdminPanel.js

const TABS = [
  { label: 'TICKERS',   path: 'tickers' },
  { label: 'QUAD SETUP', path: 'quad' },
  { label: 'USERS',     path: 'users' },
];

// Inside <Routes>:
<Route path="users" element={<UserList />} />
```

Remove the old `REACT_APP_ADMIN_PASSWORD` password gate from `AdminPanel.js`. The route is now protected by `<ProtectedRoute requireAdmin>` in `App.js`.

---

## Part 14 — Recovery script

```python
# backend/scripts/reset_admin.py

"""
Recovery script — re-seeds the admin account from env vars regardless of current state.
Run via: fly ssh console --app signal-matrix-api → python /app/scripts/reset_admin.py

Reads ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_DISPLAY_NAME from environment.
- If admin email exists: resets password, sets role=admin, status=active
- If admin email does not exist: creates the user fresh
- Idempotent — safe to run repeatedly
"""

import os
import sys
sys.path.insert(0, "/app")

from database import SessionLocal
from models.user import User
from services.auth_service import hash_password


def reset_admin():
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    name = os.getenv("ADMIN_DISPLAY_NAME", "Admin")

    if not email or not password:
        print("ERROR: ADMIN_EMAIL and ADMIN_PASSWORD must be set.")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.hashed_password = hash_password(password)
            user.role = "admin"
            user.status = "active"
            user.display_name = name
            db.commit()
            print(f"Admin reset: {email} (existing record updated)")
        else:
            user = User(
                email=email,
                display_name=name,
                hashed_password=hash_password(password),
                role="admin",
                status="active",
            )
            db.add(user)
            db.commit()
            print(f"Admin created: {email} (new record)")
    finally:
        db.close()


if __name__ == "__main__":
    reset_admin()
```

---

## Part 15 — Recovery runbook

Create `Docs/RUNBOOK_AUTH_RECOVERY.md` with the following content. This file is the documented procedure for recovering admin access if locked out.

```markdown
# Auth Recovery Runbook

## When to use

You cannot log in to https://signal.suttonmc.com — wrong password, disabled account, demoted account, or auth system bug.

## Recovery Path 1 — Direct Supabase reset (fastest, ~5 min)

1. Open Supabase dashboard → project `signal-matrix` → Table Editor → `users` table
2. Find your row. If `status` is `disabled` or `pending`, set it to `active`. If `role` is `viewer`, set it to `admin`. Save.
3. If the password is the issue: generate a new bcrypt hash on your machine:
   ```
   python -c "import bcrypt; print(bcrypt.hashpw(b'YourNewPassword123', bcrypt.gensalt()).decode())"
   ```
4. Paste the output into the `hashed_password` cell. Save.
5. Log in with the new password.

## Recovery Path 2 — Recovery script via Fly.io SSH (~10 min)

```bash
fly ssh console --app signal-matrix-api
python /app/scripts/reset_admin.py
exit
```

The script reads `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_DISPLAY_NAME` from Fly.io secrets and resets/creates the admin account.

## Recovery Path 3 — Re-seed from scratch (~15 min, last resort)

```bash
fly ssh console --app signal-matrix-api
python -c "
from database import SessionLocal
from models.user import User
db = SessionLocal()
db.query(User).delete()
db.commit()
print('All users deleted')
"
exit
fly machine restart --app signal-matrix-api
```

This nukes the users table. On restart, `seed_admin_if_empty` recreates the admin from env vars. WARNING: this also deletes every other user.

## Validation test

After deploying the auth system the first time, validate Path 1 once:
1. In Supabase, set your account `status = "disabled"`.
2. Try to log in — confirm rejected.
3. Set `status = "active"` again.
4. Confirm login works.

This confirms the runbook is accurate. Save the bcrypt-hash command in 1Password.
```

---

## Part 16 — Fly.io secrets

### API app (`signal-matrix-api`)

Generate JWT_SECRET locally first (do NOT skip this — needs to be saved in 1Password before any Fly.io action):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save the output to 1Password. Use a **different** JWT_SECRET for local dev vs production.

```bash
fly secrets set ENVIRONMENT="production" --app signal-matrix-api
fly secrets set ADMIN_EMAIL="<your-email>" --app signal-matrix-api
fly secrets set ADMIN_PASSWORD="<24-char alphanumeric — NO # $ @ , / \ ' \" |>" --app signal-matrix-api
fly secrets set ADMIN_DISPLAY_NAME="Shannon" --app signal-matrix-api
fly secrets set JWT_SECRET="<output from secrets.token_urlsafe(32)>" --app signal-matrix-api
```

**ADMIN_PASSWORD safe character set:** `a-z A-Z 0-9 ! - _ . = + ?`. Avoid `# $ @ , / \ ' " ` | & ; * < > ( ) { } [ ] ~`. Use a 1Password-generated 24-char alphanumeric password — gives ~143 bits of entropy, zero risk of shell mangling.

### Web app (`signal-matrix-web`)

Remove the obsolete client-side admin password:

```bash
fly secrets unset REACT_APP_ADMIN_PASSWORD --app signal-matrix-web
```

### Local `.env` additions

```
ENVIRONMENT=development
ADMIN_EMAIL=<same as production>
ADMIN_PASSWORD=<can match production for convenience, OR use a different local-only password>
ADMIN_DISPLAY_NAME=Shannon
JWT_SECRET=<DIFFERENT from production JWT_SECRET — never reuse>
```

Restart Docker after `.env` changes.

---

## Part 17 — Build sequence

Execute in this exact order. Confirm each step before proceeding.

### Phase A — Backend

| Step | Task |
|---|---|
| 1 | Generate JWT_SECRET locally (`python -c "import secrets; print(secrets.token_urlsafe(32))"`). Save to 1Password BEFORE anything else. |
| 2 | Alembic: create `users` table. Generate, review, `alembic upgrade head` locally, confirm in Supabase. |
| 3 | Alembic: create `password_reset_tokens` table. Same flow as Step 2. |
| 4 | `backend/models/user.py` — User model |
| 5 | `backend/models/password_reset_token.py` — PasswordResetToken model |
| 6 | `backend/services/auth_service.py` — full auth service per Part 3 |
| 7 | Update `backend/services/email_alert.py` — add `send_email_to`, `send_new_user_notification`, `send_duplicate_registration_notice`, `send_password_reset_email` per Part 4 |
| 8 | `backend/routers/auth.py` — auth router per Part 5 |
| 9 | `backend/routers/users.py` — users router per Part 6 |
| 10 | Register `auth` and `users` routers in `main.py` |
| 11 | Add session middleware to `main.py` per Part 7 |
| 12 | Add `docs_url`/`redoc_url` env-conditional to FastAPI init in `main.py` |
| 13 | Confirm CORS has `allow_credentials=True` and explicit origins |
| 14 | Add `seed_admin_if_empty` to lifespan per Part 8 |
| 15 | Register slowapi rate limiter in `main.py` per Part 5 |
| 16 | Add `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_DISPLAY_NAME`, `ENVIRONMENT=development` to local `.env`. Restart Docker. |
| 17 | `backend/scripts/reset_admin.py` — recovery script per Part 14 |
| **CHECKPOINT 1 — backend integration test** | |
| 18 | POST `/api/auth/register` with valid email + 12+ char password → 200 with pending message. Confirm Supabase row created with `status=pending`. Confirm Shannon receives new-registration email. |
| 19 | POST `/api/auth/login` for the pending account → 401 with generic error. |
| 20 | POST `/api/auth/register` with the same email again → 200 with identical pending message (no error). Confirm no duplicate row in Supabase. Confirm Shannon does NOT receive a second notification. Confirm the registered address receives a quiet "you already have an account" email. |
| 21 | POST `/api/auth/register` with 8-char password → 400 with "must be at least 12 characters". |
| 22 | POST `/api/auth/register` with `password` (in common list) → 400 with "too common". |
| 23 | Confirm seed admin account exists in Supabase (`role=admin, status=active`). Test by clearing Supabase users table, restarting Docker, confirming admin row recreated. |
| 24 | POST `/api/auth/login` as seed admin with correct password → 200 with cookie set. |
| 25 | GET `/api/auth/check` with cookie → 200 with `authenticated=true`. |
| 26 | POST `/api/auth/logout` → 200; subsequent request without cookie → 401. (Note: JWT is not blocklisted — see Deferred decisions.) |
| 27 | Hit any protected endpoint (e.g., `/api/signals/stored`) without cookie → 401. |
| 28 | Recovery script test: `python backend/scripts/reset_admin.py` locally → confirm "existing record updated" output and password actually rotates. |

### Phase B — Frontend

| Step | Task |
|---|---|
| 29 | Add `<AuthProvider>` inside `App.js` wrapping existing content — do NOT move `<BrowserRouter>` (per Part 9) |
| 29 | `src/context/AuthContext.js` — AuthContext per Part 9 |
| 30 | Add `apiFetch` to existing `src/services/api.js` — do NOT replace the file; `fetchCachedMarketData` and `fetchBatchMarketData` must be preserved (per Part 10) |
| 31 | `src/components/shared/ProtectedRoute.js` — protected route per Part 11 |
| 32 | `src/pages/LoginPage.js` per Part 12 |
| 33 | `src/pages/RegisterPage.js` per Part 12 |
| 34 | `src/pages/ForgotPasswordPage.js` per Part 12 |
| 35 | `src/pages/ResetPasswordPage.js` per Part 12 |
| 36 | Update `App.js` routes — wrap with `<ProtectedRoute>`, add auth page routes per Part 11 |
| 37 | Replace ALL `fetch(\`${API_URL}/api/...\`)` in `App.js` with `apiFetch('/api/...')` (drop the API_URL prefix; the function adds it). |
| 38 | Replace ALL `fetch(\`${API_URL}/api/...\`)` in `AdminPanel.js`, `TickerList.js`, `QuadSetup.js` with `apiFetch('/api/...')`. |
| 39 | **Verification:** `grep -rn "fetch(" src/ \| grep -v "apiFetch\|node_modules"` — every result MUST be either `AuthContext.js` (raw fetch is intentional for `/check`, `/login`, `/logout`) OR an auth page (raw fetch for register/forgot/reset since not authenticated yet). Anything else is a bug. |
| 40 | `src/components/Admin/UserList.js` per Part 13 |
| 41 | Add USERS tab to `AdminPanel.js` TABS array + Route per Part 13 |
| 42 | Remove `REACT_APP_ADMIN_PASSWORD` password gate from `AdminPanel.js` shell. Routes are now protected by `<ProtectedRoute requireAdmin>`. |

### Phase C — Local integration test

| Step | Task |
|---|---|
| 43 | Visit `localhost:3000` → redirects to `/login` ✓ |
| 44 | Log in as seed admin → reaches dashboard ✓ |
| 45 | Visit `/admin` → reaches admin panel (no second password prompt) ✓ |
| 46 | Visit `/admin/users` → user list shows seed admin row ✓ |
| 47 | Open new browser/incognito, register a new user → success message; confirm Shannon receives email with email + display name + IP + UA + timestamp ✓ |
| 48 | Try to log in as new user → 401 (pending) ✓ |
| 49 | In `/admin/users`, click Activate on the new user → status flips to Active ✓ |
| 50 | Log in as the new user (incognito window) → reaches dashboard; cannot reach `/admin` (redirected to `/`) ✓ |
| 51 | Forgot password flow: submit email → receive reset email → click link → set new password (≥ 12 chars) → redirected to login → log in with new password ✓ |
| 52 | Logout → redirects to `/login`; cookie cleared ✓ |
| 53 | Verify self-protection guards: in admin user list, confirm Disable button hidden on own row, role dropdown disabled on own row ✓ |

### Phase D — Production deploy

| Step | Task |
|---|---|
| 54 | Set Fly.io secrets: `ENVIRONMENT=production`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_DISPLAY_NAME`, `JWT_SECRET` on `signal-matrix-api`. **Use DIFFERENT JWT_SECRET than local.** |
| 55 | `fly secrets unset REACT_APP_ADMIN_PASSWORD --app signal-matrix-web` |
| 56 | Run migrations against Supabase: `fly ssh console --app signal-matrix-api` → `alembic upgrade head` → `exit`. Confirm tables created in Supabase. |
| 57 | `fly deploy --app signal-matrix-api` — deploy backend |
| 58 | `./deploy-web.sh` — deploy frontend |
| 59 | Confirm health: `fly status --app signal-matrix-api`, `fly status --app signal-matrix-web`, `curl https://api.signal.suttonmc.com/health` |

### Phase E — Production smoke test

Re-run Steps 43-53 against `https://signal.suttonmc.com`.

| Step | Task |
|---|---|
| 60 | Production: full integration test (Steps 43-53 against production URL) |
| 61 | **Schwab callback regression test:** trigger a Schwab token refresh (or wait for the 25-min auto-refresh job) → confirm callback completes successfully → check `schwab_tokens` table for updated `expires_at` |
| 62 | **CALCULATE SIGNALS regression test:** click button → confirm signals run successfully → confirm dashboard updates |
| 63 | **REFRESH DATA regression test:** click button → confirm Schwab quote fetch completes |

### Phase F — Runbook and documentation

| Step | Task |
|---|---|
| 64 | Create `Docs/RUNBOOK_AUTH_RECOVERY.md` per Part 15 |
| 65 | **Runbook validation:** in Supabase, set your account `status = "disabled"` → confirm login rejected → set `status = "active"` → confirm login works again. This proves Recovery Path 1 works. |
| 66 | Update `CLAUDE.md` with: new tables, new routers, new env vars, removed `REACT_APP_ADMIN_PASSWORD`, new project rules |
| 67 | Commit: `git add . && git commit -m "Auth + user management — JWT cookie, RBAC, admin Users tab"` |

---

## Pre-flight checklist for Neo

Before Step 1, confirm:

- [ ] Read this entire spec end to end (especially "Deferred decisions" — do not "improve" by re-adding the blocklist or hook)
- [ ] Read `CLAUDE.md` end to end
- [ ] Confirm `bcrypt`, `PyJWT`, `slowapi` are not already in `requirements.txt`
- [ ] Confirm existing `_send_email` function in `email_service.py` — match the SMTP setup pattern
- [ ] Confirm Schwab OAuth callback path is `/api/auth/schwab/callback` (verify in `routers/auth.py` if it exists, or wherever Schwab OAuth is currently implemented)
- [ ] Generate JWT_SECRET via `python -c "import secrets; print(secrets.token_urlsafe(32))"` — save to 1Password — DO NOT proceed to Step 16 without this in 1Password
- [ ] Pick ADMIN_PASSWORD: 1Password-generated, 24+ characters, alphanumeric only (no `# $ @ , / \ ' " ` | & ; * < > ( ) { } [ ] ~`)

---

## Proactive flags for Neo

1. **JWT_SECRET MUST differ between local and production.** If local dev is ever compromised, an attacker's stolen JWT must not work against production. Generate two separate values.

2. **`secure=True` cookie breaks `http://localhost:3000`.** Use `secure=IS_PRODUCTION` per Part 5. Hardcoding `secure=True` will silently break local login (cookie won't be set, requests appear successful but every subsequent call returns 401).

3. **`samesite="lax"`, NOT `"strict"`.** Strict breaks password reset email link clickthroughs. Lax still blocks CSRF POSTs.

4. **CORS `allow_credentials=True` is required.** Without it, cookies are silently stripped on cross-origin requests. The browser doesn't error — it just doesn't send the cookie.

5. **Schwab callback path stays in PUBLIC_PATHS.** Schwab's server cannot send a session cookie. Gating that path will silently break OAuth refresh.

6. **`apiFetch` 401 redirect exempts `/api/auth/check`.** AuthContext uses raw fetch for `/check`, `/login`, `/logout` precisely so the 401 redirect can never fire on those endpoints. Do not call them via `apiFetch`.

7. **`seed_admin_if_empty` is idempotent — never remove the `count() > 0` guard.** Without it, every restart attempts to recreate the admin and crashes on the unique email constraint.

8. **AdminPanel password gate must be FULLY removed.** Do not leave the old `REACT_APP_ADMIN_PASSWORD` check alongside the new `ProtectedRoute`. Double-gating with one being broken is confusing — strip the old gate cleanly.

9. **No approval notification email is sent to the user.** Shannon activates the user and tells them directly. Do not add an approval email without explicit instruction.

10. **Alembic from local Docker uses pooled connection string.** CLAUDE.md flags Supabase IPv6 issue from Docker. Alembic falls back automatically; just don't manually point it at the direct connection.

11. **The `users.py` router's `require_admin` dependency must use the LIVE DB role**, not the JWT payload role. `get_user_from_token` already loads from DB; check `user.role == "admin"` from that, not from the JWT.

12. **Cookie domain attribute is NOT set explicitly.** Default behavior — cookie scoped to the host that issued it. Both `signal.suttonmc.com` and `api.signal.suttonmc.com` are same-site (same registrable domain), so the cookie set by the API is accepted by the frontend. If you set a domain explicitly, get it right or don't set it at all.

13. **Step 39 fetch-call audit is non-negotiable.** A missed `fetch()` call without `credentials: 'include'` will silently fail with 401, redirect to `/login`, and create the appearance that auth is broken when it's actually one stray line. Run the grep, review every result.

14. **Logout is intentionally cosmetic** (clears cookie only). JWT remains valid until natural expiry. See "Deferred decisions" for rationale. Disable user in admin if true session revocation is needed.

15. **`apiFetch` is intentionally a static function with hard `window.location.href` redirect on 401.** See "Deferred decisions" for rationale. Do not refactor to a `useApiFetch` hook.

---

## Post-deployment — update CLAUDE.md

Add a section under "Known Fixes & Learnings":

```markdown
### Auth & User Management — JWT Cookie + RBAC ✅
- Replaced REACT_APP_ADMIN_PASSWORD with full session-auth layer
- JWT in httpOnly cookie, 12-hour expiry, samesite=lax, secure=production-only
- Two new tables: users, password_reset_tokens
- Self-registration → pending → admin approval flow
- Password reset via email link, 15-min token TTL
- Admin Users tab in /admin/users
- Recovery script: backend/scripts/reset_admin.py (run via fly ssh)
- Recovery runbook: Docs/RUNBOOK_AUTH_RECOVERY.md
- Rate limiting: slowapi at app level (Cloudflare WAF deferred — requires api.signal Proxied)
- Logout clears cookie only — JWT not blocklisted (deferred per spec rationale)
- See Docs/Auth_User_Management_Spec_v1.0.md for full spec including deferred decisions
```

Add to Project Rules:

```markdown
77. **Cookie config: secure=IS_PRODUCTION, samesite="lax"** — never hardcode secure=True (breaks local dev) or samesite="strict" (breaks password reset email links).
78. **Live DB role check in admin endpoints** — `require_admin` re-fetches user and checks `user.role`, never trusts the JWT role payload (which can be stale up to 12h).
79. **/api/auth/check, /api/auth/login, /api/auth/logout use raw fetch in AuthContext** — never apiFetch. /check returns 200 with authenticated:false when not logged in; never 401. apiFetch's 401 redirect would otherwise loop.
80. **No approval email to new users** — admin manually activates and notifies. Do not add an approval email without explicit instruction.
81. **Recovery: Supabase direct edit is the documented Path 1.** See Docs/RUNBOOK_AUTH_RECOVERY.md.
82. **Logout is cookie-clear only — JWT remains valid until natural expiry.** Disable user in admin for true session revocation. See Docs/Auth_User_Management_Spec_v1.0.md "Deferred decisions" for rationale.
83. **apiFetch is a static function, not a hook.** Hard navigation on 401 is intentional. See Docs/Auth_User_Management_Spec_v1.0.md "Deferred decisions" for rationale.
```

---

**End of spec. Ship it.**
