"""spx_impact_cache: add weights_date column

Revision ID: v7w8x9y0z1a2
Revises: u6v7w8x9y0z1
Create Date: 2026-05-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "v7w8x9y0z1a2"
down_revision = "u6v7w8x9y0z1"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    cols = [c["name"] for c in inspector.get_columns("spx_impact_cache")]

    if "weights_date" not in cols:
        op.add_column("spx_impact_cache", sa.Column("weights_date", sa.String(10), nullable=True))


def downgrade():
    op.drop_column("spx_impact_cache", "weights_date")
