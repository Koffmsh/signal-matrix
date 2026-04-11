"""Add h_trade_delta to signal_output

Revision ID: f3a1b9c2d4e5
Revises: e2f4a6b8c1d0
Branch Labels: None
Depends On: None
Create Date: 2026-04-10

Task 6.1 — Delta-H Trade Warning Signal.
h_trade_delta = current H_trade minus H_trade from ~20 trading days ago.
Positive = trend strengthening. Negative = trend deteriorating (early warning).
NULL when signal_history has fewer than 20 trading-day snapshots.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f3a1b9c2d4e5'
down_revision = 'e2f4a6b8c1d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('signal_output', sa.Column('h_trade_delta', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('signal_output', 'h_trade_delta')
