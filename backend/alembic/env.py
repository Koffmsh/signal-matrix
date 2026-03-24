import os
import sys
from logging.config import fileConfig
from urllib.parse import quote

from sqlalchemy import pool
from alembic import context

# ── path setup ────────────────────────────────────────────────────────────────
# Ensure backend/ is on sys.path so model imports resolve inside Docker
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # /app

# ── import all models so autogenerate sees every table ─────────────────────────
from database import Base           # noqa: E402
import models.price_cache           # noqa: E402
import models.signal_hurst          # noqa: E402
import models.signal_pivots         # noqa: E402
import models.signal_output         # noqa: E402
import models.signal_history        # noqa: E402
import models.scheduler_log         # noqa: E402
import models.ticker                # noqa: E402
import models.schwab_tokens         # noqa: E402
import models.iv_history            # noqa: E402

# ── Alembic config ─────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_migration_url() -> str:
    """
    Returns a synchronous psycopg2 URL for Alembic migrations.
    Prefers SUPABASE_CONNECTION_STRING (direct, port 5432).
    Falls back to SUPABASE_POOLED_CONNECTION_STRING (port 6543, IPv4-routable from Docker)
    when the direct connection is not available.
    Converts asyncpg-style URL to psycopg2-style and URL-encodes the password.
    """
    raw = (
        os.environ.get("SUPABASE_CONNECTION_STRING")
        or os.environ.get("SUPABASE_POOLED_CONNECTION_STRING")
    )
    if not raw:
        raise RuntimeError(
            "Neither SUPABASE_CONNECTION_STRING nor SUPABASE_POOLED_CONNECTION_STRING is set."
        )
    # Swap driver: asyncpg → psycopg2 (Alembic requires synchronous connection)
    raw = raw.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    # Swap SSL param style: asyncpg uses ssl=require, psycopg2 uses sslmode=require
    raw = raw.replace("?ssl=require", "?sslmode=require")
    raw = raw.replace("&ssl=require", "&sslmode=require")

    # URL-encode the password to handle special chars (@, #, /, etc.)
    scheme, rest = raw.split("://", 1)
    last_at = rest.rfind("@")
    userinfo = rest[:last_at]
    hostpart = rest[last_at + 1:]
    colon_idx = userinfo.find(":")
    user = userinfo[:colon_idx]
    password = userinfo[colon_idx + 1:].strip("[]")  # strip any template brackets
    encoded_password = quote(password, safe="")
    return f"{scheme}://{user}:{encoded_password}@{hostpart}"


def run_migrations_offline() -> None:
    url = _get_migration_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine as _create_engine

    # Create engine directly — avoids configparser % interpolation issues
    # with URL-encoded passwords (e.g. %40 for @).
    connectable = _create_engine(
        _get_migration_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
