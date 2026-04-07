"""iv_history: add rv21, rv63, vol_premium columns

Revision ID: b3f1c9d2e4a7
Revises: aa2d62ea88e4
Create Date: 2026-04-06

"""
from alembic import op
import sqlalchemy as sa

revision = 'b3f1c9d2e4a7'
down_revision = 'aa2d62ea88e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('iv_history', sa.Column('rv21',        sa.Float(), nullable=True))
    op.add_column('iv_history', sa.Column('rv63',        sa.Float(), nullable=True))
    op.add_column('iv_history', sa.Column('vol_premium', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('iv_history', 'vol_premium')
    op.drop_column('iv_history', 'rv63')
    op.drop_column('iv_history', 'rv21')
