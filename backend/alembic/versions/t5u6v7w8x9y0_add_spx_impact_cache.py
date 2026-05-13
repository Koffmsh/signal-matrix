"""add_spx_impact_cache table

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9
Create Date: 2026-05-13

One-row cache for SPX constituent daily impact (top 10 contributors + detractors).
Populated by the 4 PM EOD scheduler job after calculate_signals().
"""
from alembic import op
import sqlalchemy as sa


revision = "t5u6v7w8x9y0"
down_revision = "s4t5u6v7w8x9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy.engine.reflection import Inspector
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    if "spx_impact_cache" not in inspector.get_table_names():
        op.create_table(
            "spx_impact_cache",
            sa.Column("id",                sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("computed_date",     sa.String(10),  nullable=False),
            sa.Column("contributors_json", sa.Text(),      nullable=False),
            sa.Column("detractors_json",   sa.Text(),      nullable=False),
            sa.Column("spx_return_pct",    sa.Float(),     nullable=True),
            sa.Column("tickers_priced",    sa.Integer(),   nullable=True),
            sa.Column("updated_at",        sa.DateTime(),  nullable=True),
        )


def downgrade() -> None:
    op.drop_table("spx_impact_cache")
