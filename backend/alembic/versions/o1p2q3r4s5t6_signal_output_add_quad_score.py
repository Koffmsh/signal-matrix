"""signal_output_add_quad_score

Revision ID: o1p2q3r4s5t6
Revises: 312d2abdf53d
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'o1p2q3r4s5t6'
down_revision: Union[str, None] = '312d2abdf53d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("signal_output") as batch_op:
        batch_op.add_column(sa.Column("quad_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("signal_output") as batch_op:
        batch_op.drop_column("quad_score")
