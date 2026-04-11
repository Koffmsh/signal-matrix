"""Add vov_30d to price_cache and vix_regime to signal_output

Revision ID: g4b2c0d1e6f7
Revises: f3a1b9c2d4e5
Branch Labels: None
Depends On: None
Create Date: 2026-04-10

Task 6.2a — vov_30d: 30-day realized vol of VIX log returns, annualized.
             Populated on the VIX row only in price_cache.

Task 6.2b — vix_regime: VIX regime zone label stored on each signal_output row.
             Investable / Edgy / Choppy / Danger — used for debugging and future filtering.
"""
from alembic import op
import sqlalchemy as sa

revision = 'g4b2c0d1e6f7'
down_revision = 'f3a1b9c2d4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('price_cache',   sa.Column('vov_30d',    sa.Float(),        nullable=True))
    op.add_column('signal_output', sa.Column('vix_regime', sa.String(20),     nullable=True))


def downgrade() -> None:
    op.drop_column('signal_output', 'vix_regime')
    op.drop_column('price_cache',   'vov_30d')
