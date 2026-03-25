import os
from urllib.parse import quote
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


def _make_sync_url(raw: str) -> str:
    """
    Convert a postgresql+asyncpg:// URL (with potentially unencoded special
    chars in the password) to a postgresql+psycopg2:// URL safe for sync
    SQLAlchemy engine creation.
    """
    # Swap driver
    raw = raw.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    # Swap SSL param style
    raw = raw.replace("?ssl=require", "?sslmode=require")
    raw = raw.replace("&ssl=require", "&sslmode=require")

    # URL-encode the password (handles @, #, /, , etc.)
    scheme, rest = raw.split("://", 1)
    last_at = rest.rfind("@")
    userinfo = rest[:last_at]
    hostpart = rest[last_at + 1:]
    colon_idx = userinfo.find(":")
    user = userinfo[:colon_idx]
    password = userinfo[colon_idx + 1:].strip("[]")  # strip any template brackets
    encoded_password = quote(password, safe="")
    return f"{scheme}://{user}:{encoded_password}@{hostpart}"


# DATABASE_URL takes priority — use when the URL is already fully encoded (no shell-special chars).
# SUPABASE_POOLED_CONNECTION_STRING is the fallback (requires _make_sync_url encoding pass).
_db_url = os.environ.get("DATABASE_URL")
_pooled = os.environ.get("SUPABASE_POOLED_CONNECTION_STRING")

if _db_url:
    SQLALCHEMY_DATABASE_URL = _db_url
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
elif _pooled:
    SQLALCHEMY_DATABASE_URL = _make_sync_url(_pooled)
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
else:
    SQLALCHEMY_DATABASE_URL = "sqlite:///./signal_matrix.db"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
