"""Add d_extended to signal_pivots and signal_output

Revision ID: e2f4a6b8c1d0
Revises: d5e3f1a2c4b7
Branch Labels: None
Depends On: None
Create Date: 2026-04-09

Architectural clean-up (v1.7):
  EXTENDED is removed as a structural_state value.
  d_extended (Boolean) is a dedicated field that tracks whether D has pushed
  more than one BC range beyond B — the only purpose is to switch the break
  level from C to B in warn flags, popup asterisk indicator, and break state
  machine. structural_state remains clean: UPTREND_VALID, DOWNTREND_VALID,
  BREAK_OF_TRADE, BREAK_OF_TREND, BREAK_CONFIRMED, NO_STRUCTURE only.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e2f4a6b8c1d0'
down_revision = 'd5e3f1a2c4b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('signal_pivots', sa.Column('d_extended', sa.Boolean(), nullable=True))
    op.add_column('signal_output', sa.Column('d_extended', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('signal_output', 'd_extended')
    op.drop_column('signal_pivots', 'd_extended')
