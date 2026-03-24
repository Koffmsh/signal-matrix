from sqlalchemy import Column, Integer, String, Text
from database import Base


class SchwabToken(Base):
    __tablename__ = "schwab_tokens"

    id            = Column(Integer, primary_key=True)
    access_token  = Column(Text, nullable=False)   # Fernet encrypted
    refresh_token = Column(Text, nullable=False)   # Fernet encrypted
    expires_at    = Column(String)                 # ISO timestamp ET
    created_at    = Column(String)                 # UTC timestamp
    updated_at    = Column(String)                 # UTC timestamp
