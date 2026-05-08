"""add password_reset_tokens table

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-05-08

Adds the password_reset_tokens table for the forgot-password flow.
See Docs/Auth_User_Management_Spec_v1.0.md for full context.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "s4t5u6v7w8x9"
down_revision = "r3s4t5u6v7w8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"

    uuid_type = sa.CHAR(32) if is_sqlite else UUID(as_uuid=True)

    # Idempotent: skip if create_all already made the table at app startup.
    if "password_reset_tokens" not in inspector.get_table_names():
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", uuid_type, primary_key=True),
            sa.Column("user_id", uuid_type, nullable=False),
            sa.Column("token", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used", sa.Boolean(), server_default=sa.text("false"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("token", name="uq_password_reset_tokens_token"),
        )

    existing_indexes = (
        {ix["name"] for ix in inspector.get_indexes("password_reset_tokens")}
        if "password_reset_tokens" in inspector.get_table_names() else set()
    )
    if "ix_password_reset_tokens_user_id" not in existing_indexes:
        op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"], unique=False)
    if "ix_password_reset_tokens_token" not in existing_indexes:
        op.create_index("ix_password_reset_tokens_token", "password_reset_tokens", ["token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_token", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
