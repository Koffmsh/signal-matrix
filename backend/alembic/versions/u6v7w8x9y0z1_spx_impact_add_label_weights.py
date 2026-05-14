"""spx_impact: add snapshot_label and weights_json columns

Revision ID: u6v7w8x9y0z1
Revises: t5u6v7w8x9y0
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "u6v7w8x9y0z1"
down_revision = "t5u6v7w8x9y0"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    cols = [c["name"] for c in inspector.get_columns("spx_impact_cache")]

    if "snapshot_label" not in cols:
        op.add_column("spx_impact_cache", sa.Column("snapshot_label", sa.String(10), nullable=True))
        op.execute("UPDATE spx_impact_cache SET snapshot_label = 'eod' WHERE snapshot_label IS NULL")

    if "weights_json" not in cols:
        op.add_column("spx_impact_cache", sa.Column("weights_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("spx_impact_cache", "weights_json")
    op.drop_column("spx_impact_cache", "snapshot_label")
