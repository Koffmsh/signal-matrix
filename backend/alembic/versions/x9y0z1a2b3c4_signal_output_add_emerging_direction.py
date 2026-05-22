"""signal_output add emerging_direction

Revision ID: x9y0z1a2b3c4
Revises: w8x9y0z1a2b3
Create Date: 2026-05-22

Adds signal_output.emerging_direction (String) and signal_history.emerging_direction (String).
Populated for trade timeframe only when trade_direction == "Neutral" and MA50 momentum
conditions are met (price > MA50 slope, 3 consecutive closes above MA50, 22-day high breakout).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'x9y0z1a2b3c4'
down_revision = 'w8x9y0z1a2b3'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    cols = [c["name"] for c in inspector.get_columns("signal_output")]
    if "emerging_direction" not in cols:
        op.add_column("signal_output", sa.Column("emerging_direction", sa.String(10), nullable=True))

    cols_h = [c["name"] for c in inspector.get_columns("signal_history")]
    if "emerging_direction" not in cols_h:
        op.add_column("signal_history", sa.Column("emerging_direction", sa.String(10), nullable=True))


def downgrade():
    op.drop_column("signal_output", "emerging_direction")
    op.drop_column("signal_history", "emerging_direction")
