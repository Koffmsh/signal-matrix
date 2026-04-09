"""signal_output: add lrr_extended, hrr_extended columns

Revision ID: d5e3f1a2c4b7
Revises: c9a4e1f2b8d3
Create Date: 2026-04-08

Phase C — Dashboard v1.7
  lrr_extended — daily overshoot flag: today's close < prior LRR (bearish overshoot past target)
  hrr_extended — daily overshoot flag: today's close > prior HRR (bullish overshoot past target)

These are per-timeframe Boolean flags stored alongside lrr/hrr in signal_output.
Distinct from structural EXTENDED state (pivot_engine.py D > B + bc_range).
"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e3f1a2c4b7'
down_revision = 'c9a4e1f2b8d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('signal_output', sa.Column('lrr_extended', sa.Boolean(), nullable=True))
    op.add_column('signal_output', sa.Column('hrr_extended', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('signal_output', 'hrr_extended')
    op.drop_column('signal_output', 'lrr_extended')
