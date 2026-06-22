"""add alert delivery settings

Revision ID: y0z1a2b3c4d5
Revises: x9y0z1a2b3c4
Create Date: 2026-06-22

Phase 1 Alert Creator:
  - users.phone, users.alert_email_enabled, users.alert_sms_enabled
    (per-user delivery destinations + channel checkboxes)
  - user_alert_subscriptions table (per-user, per-alert on/off)

Idempotent throughout — Base.metadata.create_all() at app startup may already
have added the column/table before alembic runs on a fresh deploy (rule #90).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "y0z1a2b3c4d5"
down_revision = "x9y0z1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_type = sa.CHAR(32) if is_sqlite else UUID(as_uuid=True)

    # ── users: delivery preference columns ────────────────────────────────────
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "phone" not in user_cols:
        op.add_column("users", sa.Column("phone", sa.String(), nullable=True))
    if "alert_email_enabled" not in user_cols:
        op.add_column("users", sa.Column(
            "alert_email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "alert_sms_enabled" not in user_cols:
        op.add_column("users", sa.Column(
            "alert_sms_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))

    # ── user_alert_subscriptions table ────────────────────────────────────────
    if "user_alert_subscriptions" not in inspector.get_table_names():
        op.create_table(
            "user_alert_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", uuid_type, nullable=False),
            sa.Column("alert_type", sa.String(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", "alert_type", name="uq_user_alert_type"),
        )

    existing_tables = inspector.get_table_names()
    if "user_alert_subscriptions" in existing_tables:
        existing_idx = {ix["name"] for ix in inspector.get_indexes("user_alert_subscriptions")}
        if "ix_user_alert_subscriptions_user_id" not in existing_idx:
            op.create_index(
                "ix_user_alert_subscriptions_user_id",
                "user_alert_subscriptions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_alert_subscriptions_user_id", table_name="user_alert_subscriptions")
    op.drop_table("user_alert_subscriptions")
    op.drop_column("users", "alert_sms_enabled")
    op.drop_column("users", "alert_email_enabled")
    op.drop_column("users", "phone")
