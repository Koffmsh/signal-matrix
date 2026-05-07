"""price_cache_add_hv_rank

Revision ID: p1q2r3s4t5u6
Revises: o1p2q3r4s5t6
Create Date: 2026-05-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p1q2r3s4t5u6'
down_revision: Union[str, None] = 'o1p2q3r4s5t6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("price_cache") as batch_op:
        batch_op.add_column(sa.Column("hv_rank", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("price_cache") as batch_op:
        batch_op.drop_column("hv_rank")
