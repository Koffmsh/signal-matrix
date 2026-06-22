"""
user_alert_subscription.py — per-user, per-alert on/off toggles.

One row per (user, alert_type). enabled=True means that user receives that
alert via whichever channels they have turned on (account email / phone).
The delivery destinations themselves live on the users table (Phase 1:
one email + one phone shared across all of a user's alerts).

alert_type values match the keys the intraday monitor fires:
  'PROXIMITY' | 'RETRACEMENT_50'
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from database import Base
from datetime import datetime, timezone


class UserAlertSubscription(Base):
    __tablename__ = "user_alert_subscriptions"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(UUID(as_uuid=True), nullable=False, index=True)
    alert_type = Column(String, nullable=False)
    enabled    = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "alert_type", name="uq_user_alert_type"),
    )
