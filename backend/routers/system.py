"""
System status endpoint — single source of truth for the header indicators.

Admin → {connection, data, status}.   Regular/anon user → {status} only.
Role is checked live from the cookie (never trusts a stale JWT payload), but does
NOT raise — an unauthenticated visitor still gets the user-facing `status` dot.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from services import system_status as sysstat
from services.auth_service import get_user_from_token, COOKIE_NAME

router = APIRouter(prefix="/api/system", tags=["system"])


def _is_admin(request: Request, db: Session) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    user  = get_user_from_token(token, db) if token else None
    return bool(user and user.status == "active" and user.role == "admin")


@router.get("/status")
def system_status(request: Request, db: Session = Depends(get_db)):
    full = sysstat.get_system_status(db)
    if _is_admin(request, db):
        return full
    # Regular users see only the plain-language roll-up.
    return {"status": full["status"]}
