"""rename_iv_history_to_vol_history

Revision ID: n1o2p3q4r5s6
Revises: 08f62d15c8b7
Create Date: 2026-04-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'n1o2p3q4r5s6'
down_revision: Union[str, None] = '08f62d15c8b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    # create_all on startup may have already created vol_history (empty) — drop it first
    if 'vol_history' in existing_tables:
        op.drop_table('vol_history')

    # Rename iv_history → vol_history (preserves all data and existing constraints)
    op.rename_table('iv_history', 'vol_history')

    # Rename the unique constraint to match the new table name
    with op.batch_alter_table('vol_history') as batch_op:
        batch_op.drop_constraint('uix_iv_history_ticker_date', type_='unique')
        batch_op.create_unique_constraint('uix_vol_history_ticker_date', ['ticker', 'iv_date'])


def downgrade() -> None:
    with op.batch_alter_table('vol_history') as batch_op:
        batch_op.drop_constraint('uix_vol_history_ticker_date', type_='unique')
        batch_op.create_unique_constraint('uix_iv_history_ticker_date', ['ticker', 'iv_date'])

    op.rename_table('vol_history', 'iv_history')
