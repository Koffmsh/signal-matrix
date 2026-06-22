from sqlalchemy import Column, String, DateTime, Boolean
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
    role            = Column(String, nullable=False, default="viewer")
    status          = Column(String, nullable=False, default="pending")
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login      = Column(DateTime(timezone=True), nullable=True)

    # ── Alert delivery preferences (Phase 1 Alert Creator) ───────────────────
    # The account email above is the email destination; alert_email_enabled is
    # the per-user "send me email alerts" checkbox. phone + alert_sms_enabled
    # are the SMS channel (delivery still gated globally until 10DLC clears).
    phone               = Column(String,  nullable=True)
    alert_email_enabled = Column(Boolean, nullable=False, default=False)
    alert_sms_enabled   = Column(Boolean, nullable=False, default=False)
