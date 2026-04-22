"""iv_history_add_skew_rank

Revision ID: 08f62d15c8b7
Revises: m3c4d5e6f7g8
Create Date: 2026-04-22 02:01:30.680854

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '08f62d15c8b7'
down_revision: Union[str, None] = 'm3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('iv_history', sa.Column('skew_rank', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('iv_history', 'skew_rank')
