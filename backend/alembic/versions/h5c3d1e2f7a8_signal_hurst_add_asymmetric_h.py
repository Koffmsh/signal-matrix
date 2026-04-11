"""Add h_trend_up and h_trend_down to signal_hurst

Revision ID: h5c3d1e2f7a8
Revises: g4b2c0d1e6f7
Branch Labels: None
Depends On: None
Create Date: 2026-04-10

Task 6.3 — Asymmetric H for Commodities and FX.
h_trend_up:   DFA H computed on positive-return days (252-bar lookback)
h_trend_down: DFA H computed on negative-return days (252-bar lookback)

Used in conviction base score for Commodities and Foreign Exchange:
  Bullish viewpoint → h_trend_up (or symmetric h_trend if unavailable)
  Bearish viewpoint → h_trend_down (or symmetric h_trend if unavailable)

Ineligible asset classes (Domestic Equities etc.) remain NULL.
/ZN excluded explicitly despite Commodities classification.
"""
from alembic import op
import sqlalchemy as sa

revision = 'h5c3d1e2f7a8'
down_revision = 'g4b2c0d1e6f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('signal_hurst', sa.Column('h_trend_up',   sa.Float(), nullable=True))
    op.add_column('signal_hurst', sa.Column('h_trend_down', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('signal_hurst', 'h_trend_down')
    op.drop_column('signal_hurst', 'h_trend_up')
