"""add ai_summaries table

Revision ID: b3c4d5e6f7g8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-03

New table for per-ticker AI-generated narrative summaries (Security Detail page).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'b3c4d5e6f7g8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    if "ai_summaries" not in inspector.get_table_names():
        op.create_table(
            "ai_summaries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ticker", sa.String(), nullable=False, index=True),
            sa.Column("summary_date", sa.String(10), nullable=False),
            sa.Column("headline", sa.Text(), nullable=True),
            sa.Column("bullets_json", sa.Text(), nullable=True),
            sa.Column("model", sa.String(50), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.UniqueConstraint("ticker", "summary_date", name="uq_ai_summary_ticker_date"),
        )


def downgrade():
    op.drop_table("ai_summaries")
