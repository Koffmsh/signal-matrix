"""signal_output add quad fields

Revision ID: 671aab571fcd
Revises: d352e36b3876
Create Date: 2026-04-23 16:04:34.095172

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '671aab571fcd'
down_revision: Union[str, None] = 'd352e36b3876'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('signal_output',
        sa.Column('quad_alignment', sa.String(20), nullable=True))
    op.add_column('signal_output',
        sa.Column('quad_mult', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('signal_output', 'quad_mult')
    op.drop_column('signal_output', 'quad_alignment')
