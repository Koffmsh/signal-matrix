"""Add ATR to price_cache

Revision ID: j7e5f3g1h2i0
Revises: f7a3b2c1d9e6
Branch Labels: None
Depends On: None
Create Date: 2026-04-14

Adds 14-day Average True Range (ATR) to price_cache.

ATR = simple MA of True Range over 14 days
TR[i] = max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1]))

Used in conviction_engine.compute_trade_lrr_hrr():
  Downtrend + normal (below MA20, tight HRR):
    HRR = max(MA20_TP, close + 0.5×ATR)
  When price is within half an ATR of MA20_TP, ATR buffer takes over
  to ensure a meaningful ceiling above the current close.
  The 2-consecutive-close-above-MA20 flip to BB upper is unchanged.
"""
from alembic import op
import sqlalchemy as sa


revision = 'j7e5f3g1h2i0'
down_revision = 'f7a3b2c1d9e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('price_cache', sa.Column('atr', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('price_cache', 'atr')
