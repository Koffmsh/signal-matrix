"""add_intraday_alert_log

Revision ID: a1b2c3d4e5f6
Revises: e6d00527381b
Create Date: 2026-04-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e6d00527381b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'intraday_alert_log',
        sa.Column('id',         sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('ticker',     sa.String(),  nullable=False),
        sa.Column('alert_date', sa.String(),  nullable=False),
        sa.Column('alert_type', sa.String(),  nullable=False),
        sa.Column('pivot_c',    sa.Float(),   nullable=True),
        sa.Column('fired_at',   sa.String(),  nullable=False),
        sa.Column('price',      sa.Float(),   nullable=False),
        sa.Column('metric',     sa.Float(),   nullable=True),
        sa.Column('conviction', sa.Float(),   nullable=True),
        sa.Column('created_at', sa.String(),  nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'ticker', 'alert_date', 'alert_type', 'pivot_c',
            name='uq_intraday_alert_ticker_date_type_c'
        ),
    )
    op.create_index('ix_intraday_alert_log_ticker', 'intraday_alert_log', ['ticker'])
    op.create_index('ix_intraday_alert_log_date',   'intraday_alert_log', ['alert_date'])


def downgrade() -> None:
    op.drop_index('ix_intraday_alert_log_date',   table_name='intraday_alert_log')
    op.drop_index('ix_intraday_alert_log_ticker', table_name='intraday_alert_log')
    op.drop_table('intraday_alert_log')
