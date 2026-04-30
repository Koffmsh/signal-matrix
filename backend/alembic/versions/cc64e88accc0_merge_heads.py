"""merge_heads

Revision ID: cc64e88accc0
Revises: a1b2c3d4e5f6, n1o2p3q4r5s6
Create Date: 2026-04-30 20:10:53.347590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc64e88accc0'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', 'n1o2p3q4r5s6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
