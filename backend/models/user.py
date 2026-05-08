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
    role            = Column(String, nullable=False, default="viewer")
    status          = Column(String, nullable=False, default="pending")
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login      = Column(DateTime(timezone=True), nullable=True)
