"""add_snap_state_columns

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-05-07 00:00:00.000000

Adds hrr_snapped / lrr_snapped boolean columns to signal_output and
signal_history for the v1.9.1 Trade RR BB+Snap formula.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'q2r3s4t5u6v7'
down_revision: Union[str, None] = 'p1q2r3s4t5u6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("signal_output") as batch_op:
        batch_op.add_column(sa.Column("hrr_snapped", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("lrr_snapped", sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table("signal_history") as batch_op:
        batch_op.add_column(sa.Column("hrr_snapped", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("lrr_snapped", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("signal_history") as batch_op:
        batch_op.drop_column("lrr_snapped")
        batch_op.drop_column("hrr_snapped")

    with op.batch_alter_table("signal_output") as batch_op:
        batch_op.drop_column("lrr_snapped")
        batch_op.drop_column("hrr_snapped")
