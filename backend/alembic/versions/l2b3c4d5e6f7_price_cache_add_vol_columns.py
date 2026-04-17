"""price_cache: add volatility columns (hv30, hv90, iv30, risk_reversal, skew_rank, put_call_ratio)

Revision ID: l2b3c4d5e6f7
Revises: k1a2b3c4d5e6
Branch Labels: None
Depends On: None
Create Date: 2026-04-17

Adds per-ticker volatility metrics for popup display:
  - hv30          — 21-day (HV30) annualized realized vol (decimal, e.g. 0.196 = 19.6%)
  - hv90          — 63-day (HV90) annualized realized vol
  - iv30          — raw 30-day constant-maturity implied vol from Schwab options chain
  - risk_reversal — 25Δ call IV - 25Δ put IV; positive = forward skew = bullish signal
  - skew_rank     — RR rank within 252-day rolling history (0-100), same method as IV Rank
  - put_call_ratio — total put OI / total call OI across fetched chain
"""
from alembic import op
import sqlalchemy as sa


revision = 'l2b3c4d5e6f7'
down_revision = 'k1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('price_cache', sa.Column('hv30',           sa.Float(), nullable=True))
    op.add_column('price_cache', sa.Column('hv90',           sa.Float(), nullable=True))
    op.add_column('price_cache', sa.Column('iv30',           sa.Float(), nullable=True))
    op.add_column('price_cache', sa.Column('risk_reversal',  sa.Float(), nullable=True))
    op.add_column('price_cache', sa.Column('skew_rank',      sa.Integer(), nullable=True))
    op.add_column('price_cache', sa.Column('put_call_ratio', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('price_cache', 'put_call_ratio')
    op.drop_column('price_cache', 'skew_rank')
    op.drop_column('price_cache', 'risk_reversal')
    op.drop_column('price_cache', 'iv30')
    op.drop_column('price_cache', 'hv90')
    op.drop_column('price_cache', 'hv30')
