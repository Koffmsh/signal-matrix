"""price_cache add ath

Revision ID: w8x9y0z1a2b3
Revises: v7w8x9y0z1a2
Create Date: 2026-05-22

Adds price_cache.ath (Float) — all-time high from 5-year price history.
Computed at write time in all history-writing code paths.
Exposed as scalar in serialize_cache_row() to avoid re-loading history_json blob.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'w8x9y0z1a2b3'
down_revision = 'v7w8x9y0z1a2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    cols = [c["name"] for c in inspector.get_columns("price_cache")]
    if "ath" not in cols:
        op.add_column("price_cache", sa.Column("ath", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("price_cache", "ath")
