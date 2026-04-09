"""price_cache: add std20, ma200, ma20_regime columns

Revision ID: c9a4e1f2b8d3
Revises: b3f1c9d2e4a7
Create Date: 2026-04-08

Phase A — Risk Range Engine Revamp (v1.7)
  std20      — 21-day realized vol in dollar terms (STD20 = std(log_returns[-21:]) × close)
  ma200      — 200-day simple moving average (Tail Level floor/ceiling)
  ma20_regime — 'uptrend' | 'downtrend' — 2-consecutive-close rule vs MA20

ma20, ma50, ma100 already exist from initial_schema migration.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9a4e1f2b8d3'
down_revision = 'b3f1c9d2e4a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('price_cache', sa.Column('std20',       sa.Float(), nullable=True))
    op.add_column('price_cache', sa.Column('ma200',       sa.Float(), nullable=True))
    op.add_column('price_cache', sa.Column('ma20_regime', sa.Text(),  nullable=True))


def downgrade() -> None:
    op.drop_column('price_cache', 'ma20_regime')
    op.drop_column('price_cache', 'ma200')
    op.drop_column('price_cache', 'std20')
