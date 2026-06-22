"""
alerts.py — per-user alert delivery settings (Phase 1 Alert Creator).

  GET /api/alerts/my-settings   → the logged-in user's delivery channels +
                                   per-alert on/off, plus the alert catalog.
  PUT /api/alerts/my-settings   → save them ("Apply settings" button).

Operates on the logged-in user's own row (request.state.user, set by the
session middleware in main.py). Not admin-gated — any active user manages
their own alerts. Generalizes to a user-facing settings page later with no
schema change.
"""
import re
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.user_alert_subscription import UserAlertSubscription
from services.sms import SMS_DISABLED
from services.alert_catalog import ALERT_CATALOG, ALERT_KEYS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# Light E.164-ish validation: optional +, 7–15 digits.
_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


class SaveSettingsRequest(BaseModel):
    email_enabled: bool
    sms_enabled: bool
    phone: str | None = None
    alerts: dict[str, bool]   # { "PROXIMITY": true, "RETRACEMENT_50": false }


def _current_user(request: Request, db: Session) -> User:
    """Re-fetch the authenticated user into this request's session.
    request.state.user is set by the middleware but is detached."""
    state_user = getattr(request.state, "user", None)
    if not state_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = db.query(User).filter(User.id == state_user.id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


@router.get("/my-settings")
def get_my_settings(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)

    subs = {
        s.alert_type: s.enabled
        for s in db.query(UserAlertSubscription).filter(
            UserAlertSubscription.user_id == user.id
        ).all()
    }

    return {
        "email": user.email,                      # read-only account email
        "email_enabled": bool(user.alert_email_enabled),
        "phone": user.phone,
        "sms_enabled": bool(user.alert_sms_enabled),
        "sms_globally_disabled": SMS_DISABLED,     # UI shows "pending carrier registration"
        "alerts": [
            {
                "key": a["key"],
                "label": a["label"],
                "description": a["description"],
                "enabled": subs.get(a["key"], False),
            }
            for a in ALERT_CATALOG
        ],
    }


@router.put("/my-settings")
def save_my_settings(req: SaveSettingsRequest, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)

    # Validate phone if SMS requested / phone provided
    phone = (req.phone or "").strip() or None
    if phone and not _PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="Enter a valid phone number (e.g. +14155551234)")
    if req.sms_enabled and not phone:
        raise HTTPException(status_code=400, detail="Add a phone number to enable SMS alerts")

    # Reject unknown alert keys rather than silently dropping them
    unknown = set(req.alerts) - ALERT_KEYS
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown alert(s): {', '.join(sorted(unknown))}")

    # ── Delivery channels (on the user row) ──────────────────────────────────
    user.alert_email_enabled = req.email_enabled
    user.alert_sms_enabled   = req.sms_enabled
    user.phone               = phone

    # ── Per-alert subscriptions (upsert) ─────────────────────────────────────
    existing = {
        s.alert_type: s
        for s in db.query(UserAlertSubscription).filter(
            UserAlertSubscription.user_id == user.id
        ).all()
    }
    now = datetime.now(timezone.utc)
    for key in ALERT_KEYS:
        enabled = bool(req.alerts.get(key, existing.get(key).enabled if key in existing else False))
        row = existing.get(key)
        if row:
            row.enabled = enabled
            row.updated_at = now
        else:
            db.add(UserAlertSubscription(
                user_id=user.id, alert_type=key, enabled=enabled, updated_at=now))

    db.commit()
    logger.info(f"Alert settings saved for {user.email}")
    return {"ok": True}
