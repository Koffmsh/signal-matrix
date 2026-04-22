"""price_cache_add_vrp_changes

Revision ID: 7d8a7841272e
Revises: 08f62d15c8b7
Create Date: 2026-04-22 07:06:46.675421

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d8a7841272e'
down_revision: Union[str, None] = '08f62d15c8b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('price_cache', sa.Column('vrp_1d_chg', sa.Float(), nullable=True))
    op.add_column('price_cache', sa.Column('vrp_1w_chg', sa.Float(), nullable=True))
    op.add_column('price_cache', sa.Column('vrp_1m_chg', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('price_cache', 'vrp_1m_chg')
    op.drop_column('price_cache', 'vrp_1w_chg')
    op.drop_column('price_cache', 'vrp_1d_chg')
