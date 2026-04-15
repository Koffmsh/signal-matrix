"""price_cache_drop_tp_columns

Revision ID: 13fb636fe76a
Revises: j7e5f3g1h2i0
Branch Labels: None
Depends On: None
Create Date: 2026-04-15

Drops ma20_tp and std20_tp from price_cache.

These were used as center for the BB LRR/HRR formula (v1.8 interim),
but the improvement over standard MA20(close) was negligible (±7 pts on SPX).
Formula now uses MA20(close) as center directly.

H/L history (history_high_json, history_low_json) is retained for ATR calculation.
"""
from alembic import op
import sqlalchemy as sa


revision = '13fb636fe76a'
down_revision = 'j7e5f3g1h2i0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('price_cache', 'ma20_tp')
    op.drop_column('price_cache', 'std20_tp')


def downgrade() -> None:
    op.add_column('price_cache', sa.Column('std20_tp', sa.Float(), nullable=True))
    op.add_column('price_cache', sa.Column('ma20_tp',  sa.Float(), nullable=True))
