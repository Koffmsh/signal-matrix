"""vol_history_implied_vol_nullable

Revision ID: 312d2abdf53d
Revises: cc64e88accc0
Create Date: 2026-04-30 20:11:00.188045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '312d2abdf53d'
down_revision: Union[str, None] = 'cc64e88accc0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("vol_history") as batch_op:
        batch_op.alter_column("implied_vol", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("vol_history") as batch_op:
        batch_op.alter_column("implied_vol", existing_type=sa.Float(), nullable=False)
