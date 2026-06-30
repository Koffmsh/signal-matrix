"""price_cache enforce UNIQUE(ticker)

Revision ID: z1a2b3c4d5e6
Revises: y0z1a2b3c4d5
Create Date: 2026-06-30

Production never enforced UNIQUE(ticker) on price_cache: the model declared only
index=True, and Base.metadata.create_all() never ALTERs an existing table to add
a constraint. That allowed a duplicate ROBO row (a stale yahoo_fallback orphan)
to persist and non-deterministically poison the dashboard read. This migration:
  1. De-duplicates price_cache, keeping one row per ticker (latest updated_at,
     then highest id) — a no-op on an already-clean DB.
  2. Converts the existing non-unique ix_price_cache_ticker index to UNIQUE.

Idempotent (rule #90): on a fresh DB, create_all() now builds the index as unique
(model gained unique=True), so the conversion is skipped when already unique.
Postgres-specific (DISTINCT ON) — dev + prod are both Postgres (ADR-025).
"""
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "z1a2b3c4d5e6"
down_revision = "y0z1a2b3c4d5"
branch_labels = None
depends_on = None

_IDX = "ix_price_cache_ticker"


def _ticker_index_is_unique(bind) -> bool:
    for ix in inspect(bind).get_indexes("price_cache"):
        if ix["name"] == _IDX:
            return bool(ix.get("unique"))
    return False


def upgrade() -> None:
    bind = op.get_bind()
    if _ticker_index_is_unique(bind):
        return  # already enforced (fresh DB via create_all) — nothing to do

    # 1 — collapse duplicates, keeping the latest-updated row per ticker
    op.execute(
        """
        DELETE FROM price_cache p
        WHERE p.id NOT IN (
            SELECT DISTINCT ON (ticker) id
            FROM price_cache
            ORDER BY ticker, updated_at DESC NULLS LAST, id DESC
        )
        """
    )

    # 2 — convert the non-unique index to unique
    op.drop_index(_IDX, table_name="price_cache")
    op.create_index(_IDX, "price_cache", ["ticker"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    if not _ticker_index_is_unique(bind):
        return
    op.drop_index(_IDX, table_name="price_cache")
    op.create_index(_IDX, "price_cache", ["ticker"], unique=False)
