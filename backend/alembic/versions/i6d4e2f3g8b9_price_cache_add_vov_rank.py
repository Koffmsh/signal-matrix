"""Add vov_rank to price_cache

Revision ID: i6d4e2f3g8b9
Revises: h5c3d1e2f7a8
Branch Labels: None
Depends On: None
Create Date: 2026-04-10

Task 6.2a addendum — VoV percentile rank computable immediately from 5 years of
VIX price history already stored in price_cache. No need to accumulate 252 days
of stored VoV values — the rolling series is derived on the fly at signal time.
"""
from alembic import op
import sqlalchemy as sa

revision = 'i6d4e2f3g8b9'
down_revision = 'h5c3d1e2f7a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('price_cache', sa.Column('vov_rank', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('price_cache', 'vov_rank')
