"""Add OHLC history and typical-price metrics to price_cache

Revision ID: f7a3b2c1d9e6
Revises: e2f4a6b8c1d0
Branch Labels: None
Depends On: None
Create Date: 2026-04-14

Adds daily high/low, rolling high/low history arrays, and MA20/STD20 of
typical price (H+L+C)/3 to price_cache.  The typical-price center resists
slicing lower during selloffs (close-on-lows days) and stays low during
recoveries (close-on-highs days), producing more stable LRR/HRR levels than
close-based Bollinger Bands alone.

conviction_engine.compute_trade_lrr_hrr() uses ma20_tp/std20_tp when
populated; falls back to ma20/std20 (close-based) during the warmup period
while OHLC history accumulates.

_history_fetch_mode() now forces a "short" re-fetch for any ticker whose
history_high_json is NULL — this runs once per ticker on the first REFRESH
DATA after deployment, populating ~22 bars of OHLC (enough for MA20).
"""
from alembic import op
import sqlalchemy as sa


revision = 'f7a3b2c1d9e6'
down_revision = 'i6d4e2f3g8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('price_cache', sa.Column('daily_high',        sa.Float(),   nullable=True))
    op.add_column('price_cache', sa.Column('daily_low',         sa.Float(),   nullable=True))
    op.add_column('price_cache', sa.Column('history_high_json', sa.Text(),    nullable=True))
    op.add_column('price_cache', sa.Column('history_low_json',  sa.Text(),    nullable=True))
    op.add_column('price_cache', sa.Column('ma20_tp',           sa.Float(),   nullable=True))
    op.add_column('price_cache', sa.Column('std20_tp',          sa.Float(),   nullable=True))


def downgrade() -> None:
    op.drop_column('price_cache', 'std20_tp')
    op.drop_column('price_cache', 'ma20_tp')
    op.drop_column('price_cache', 'history_low_json')
    op.drop_column('price_cache', 'history_high_json')
    op.drop_column('price_cache', 'daily_low')
    op.drop_column('price_cache', 'daily_high')
