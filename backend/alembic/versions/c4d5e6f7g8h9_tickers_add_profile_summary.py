"""tickers add profile_summary

Revision ID: c4d5e6f7g8h9
Revises: b3c4d5e6f7g8
Create Date: 2026-08-03

One-time security description fetched from yfinance on ticker creation.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'c4d5e6f7g8h9'
down_revision = 'b3c4d5e6f7g8'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = [c["name"] for c in inspector.get_columns("tickers")]

    if "profile_summary" not in existing:
        op.add_column("tickers", sa.Column("profile_summary", sa.String(), nullable=True))


def downgrade():
    op.drop_column("tickers", "profile_summary")
