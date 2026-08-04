"""signal_output + signal_history add pillar score columns

Revision ID: a2b3c4d5e6f7
Revises: z1a2b3c4d5e6
Create Date: 2026-08-03

Adds structural_score, volume_score, vix_score to signal_output (trade tf only).
Adds structural_score, volume_score, vix_score, quad_score to signal_history.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'a2b3c4d5e6f7'
down_revision = 'z1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    so_cols = [c["name"] for c in inspector.get_columns("signal_output")]
    for col in ("structural_score", "volume_score", "vix_score"):
        if col not in so_cols:
            op.add_column("signal_output", sa.Column(col, sa.Integer(), nullable=True))

    sh_cols = [c["name"] for c in inspector.get_columns("signal_history")]
    for col in ("structural_score", "volume_score", "vix_score", "quad_score"):
        if col not in sh_cols:
            op.add_column("signal_history", sa.Column(col, sa.Integer(), nullable=True))


def downgrade():
    for col in ("structural_score", "volume_score", "vix_score"):
        op.drop_column("signal_output", col)
    for col in ("structural_score", "volume_score", "vix_score", "quad_score"):
        op.drop_column("signal_history", col)
