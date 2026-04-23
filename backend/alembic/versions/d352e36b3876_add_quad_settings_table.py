"""add quad_settings table

Revision ID: d352e36b3876
Revises: 7d8a7841272e
Create Date: 2026-04-23 16:03:47.538239

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd352e36b3876'
down_revision: Union[str, None] = '7d8a7841272e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quad_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('current_quad', sa.Integer(), nullable=False),
        sa.Column('current_prob', sa.Float(), nullable=False),
        sa.Column('next_quad', sa.Integer(), nullable=True),
        sa.Column('next_prob', sa.Float(), nullable=True),
        sa.Column('effective_date', sa.String(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('quad_settings')
