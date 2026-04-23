"""redesign_quad_settings_monthly_grid

Revision ID: e6d00527381b
Revises: 671aab571fcd
Create Date: 2026-04-23 17:14:15.349926

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6d00527381b'
down_revision: Union[str, None] = '671aab571fcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('quad_settings')
    op.create_table(
        'quad_settings',
        sa.Column('id',             sa.Integer(),     nullable=False),
        sa.Column('country',        sa.String(10),    nullable=False, server_default='US'),
        sa.Column('forecast_month', sa.String(7),     nullable=False),
        sa.Column('quad',           sa.Integer(),     nullable=False),
        sa.Column('probability',    sa.Float(),       nullable=False),
        sa.Column('quad_type',      sa.String(20),    nullable=False, server_default='monthly'),
        sa.Column('notes',          sa.Text(),        nullable=True),
        sa.Column('created_at',     sa.String(),      nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('country', 'forecast_month', 'quad_type',
                            name='uq_quad_country_month_type'),
    )


def downgrade() -> None:
    op.drop_table('quad_settings')
    op.create_table(
        'quad_settings',
        sa.Column('id',             sa.Integer(),  nullable=False),
        sa.Column('current_quad',   sa.Integer(),  nullable=False),
        sa.Column('current_prob',   sa.Float(),    nullable=False),
        sa.Column('next_quad',      sa.Integer(),  nullable=True),
        sa.Column('next_prob',      sa.Float(),    nullable=True),
        sa.Column('effective_date', sa.String(),   nullable=False),
        sa.Column('notes',          sa.Text(),     nullable=True),
        sa.Column('created_at',     sa.String(),   nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
