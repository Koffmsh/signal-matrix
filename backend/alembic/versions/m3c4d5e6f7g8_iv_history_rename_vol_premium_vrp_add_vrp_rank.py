"""iv_history: rename vol_premium→vrp; price_cache: add vrp_rank

Revision ID: m3c4d5e6f7g8
Revises: l2b3c4d5e6f7
Branch Labels: None
Depends On: None
Create Date: 2026-04-20

Changes:
  - iv_history.vol_premium  → iv_history.vrp
      (Vol Risk Premium = IV30 − HV30; rename aligns with VRP Rank naming)
  - price_cache.vrp_rank    added (Integer, nullable)
      (VRP rank within 252-day rolling history, 0-100, same methodology as IV Rank)
"""
from alembic import op
import sqlalchemy as sa


revision = 'm3c4d5e6f7g8'
down_revision = 'l2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_context().dialect.name

    if dialect == 'sqlite':
        # SQLite requires table recreation for column renames
        with op.batch_alter_table('iv_history', recreate='always') as batch_op:
            batch_op.alter_column('vol_premium', new_column_name='vrp', existing_type=sa.Float())

        with op.batch_alter_table('price_cache', recreate='always') as batch_op:
            batch_op.add_column(sa.Column('vrp_rank', sa.Integer(), nullable=True))
    else:
        # PostgreSQL supports RENAME COLUMN directly
        op.alter_column('iv_history', 'vol_premium', new_column_name='vrp')
        op.add_column('price_cache', sa.Column('vrp_rank', sa.Integer(), nullable=True))


def downgrade() -> None:
    dialect = op.get_context().dialect.name

    if dialect == 'sqlite':
        with op.batch_alter_table('iv_history', recreate='always') as batch_op:
            batch_op.alter_column('vrp', new_column_name='vol_premium', existing_type=sa.Float())

        with op.batch_alter_table('price_cache', recreate='always') as batch_op:
            batch_op.drop_column('vrp_rank')
    else:
        op.alter_column('iv_history', 'vrp', new_column_name='vol_premium')
        op.drop_column('price_cache', 'vrp_rank')
