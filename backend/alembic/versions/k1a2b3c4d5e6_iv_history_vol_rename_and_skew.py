"""iv_history: rename rv21/rv63 to hv30/hv90, add skew + P/C columns

Revision ID: k1a2b3c4d5e6
Revises: 13fb636fe76a
Branch Labels: None
Depends On: None
Create Date: 2026-04-17

Changes:
  - rv21 → hv30  (21 trading days ≈ 30 calendar days — naming aligns with IV30 tenor)
  - rv63 → hv90  (63 trading days ≈ 90 calendar days)
  - Add call_iv_25d  — IV of 25-delta OTM call (30d constant maturity)
  - Add put_iv_25d   — IV of 25-delta OTM put
  - Add risk_reversal — call_iv_25d - put_iv_25d; positive = forward skew = bullish
  - Add put_call_ratio — total put OI / total call OI across fetched chain
"""
from alembic import op
import sqlalchemy as sa


revision = 'k1a2b3c4d5e6'
down_revision = '13fb636fe76a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_context().dialect.name

    if dialect == 'sqlite':
        # SQLite requires table recreation for column renames
        with op.batch_alter_table('iv_history', recreate='always') as batch_op:
            batch_op.alter_column('rv21', new_column_name='hv30', existing_type=sa.Float())
            batch_op.alter_column('rv63', new_column_name='hv90', existing_type=sa.Float())
            batch_op.add_column(sa.Column('call_iv_25d',    sa.Float(), nullable=True))
            batch_op.add_column(sa.Column('put_iv_25d',     sa.Float(), nullable=True))
            batch_op.add_column(sa.Column('risk_reversal',  sa.Float(), nullable=True))
            batch_op.add_column(sa.Column('put_call_ratio', sa.Float(), nullable=True))
    else:
        # PostgreSQL supports RENAME COLUMN directly
        op.alter_column('iv_history', 'rv21', new_column_name='hv30')
        op.alter_column('iv_history', 'rv63', new_column_name='hv90')
        op.add_column('iv_history', sa.Column('call_iv_25d',    sa.Float(), nullable=True))
        op.add_column('iv_history', sa.Column('put_iv_25d',     sa.Float(), nullable=True))
        op.add_column('iv_history', sa.Column('risk_reversal',  sa.Float(), nullable=True))
        op.add_column('iv_history', sa.Column('put_call_ratio', sa.Float(), nullable=True))


def downgrade() -> None:
    dialect = op.get_context().dialect.name

    if dialect == 'sqlite':
        with op.batch_alter_table('iv_history', recreate='always') as batch_op:
            batch_op.alter_column('hv30', new_column_name='rv21', existing_type=sa.Float())
            batch_op.alter_column('hv90', new_column_name='rv63', existing_type=sa.Float())
            batch_op.drop_column('call_iv_25d')
            batch_op.drop_column('put_iv_25d')
            batch_op.drop_column('risk_reversal')
            batch_op.drop_column('put_call_ratio')
    else:
        op.drop_column('iv_history', 'put_call_ratio')
        op.drop_column('iv_history', 'risk_reversal')
        op.drop_column('iv_history', 'put_iv_25d')
        op.drop_column('iv_history', 'call_iv_25d')
        op.alter_column('iv_history', 'hv30', new_column_name='rv21')
        op.alter_column('iv_history', 'hv90', new_column_name='rv63')
