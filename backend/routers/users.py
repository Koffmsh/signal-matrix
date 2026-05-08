"""
users.py — Admin user management endpoints.

GET   /api/users                         → list all users
PATCH /api/users/{user_id}               → update status / role / display_name
POST  /api/users/{user_id}/reset-password → admin sets new password directly
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from services.auth_service import (
    hash_password,
    validate_password_strength,
    get_user_from_token,
    COOKIE_NAME,
)


router = APIRouter(prefix="/api/users", tags=["users"])


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
