"""add users table

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-05-08

Adds the users table for JWT cookie auth and RBAC.
See Docs/Auth_User_Management_Spec_v1.0.md for full context.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "r3s4t5u6v7w8"
down_revision = "q2r3s4t5u6v7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"

    # Use UUID(as_uuid=True) on Postgres; on SQLite, SQLAlchemy stores UUID as CHAR(32) string.
    uuid_type = sa.CHAR(32) if is_sqlite else UUID(as_uuid=True)

    # Idempotent: skip if create_all already made the table at app startup
    # (main.py runs Base.metadata.create_all on boot).
    if "users" not in inspector.get_table_names():
        op.create_table(
            "users",
            sa.Column("id", uuid_type, primary_key=True),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False, server_default="viewer"),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("users")} if "users" in inspector.get_table_names() else set()
    if "ix_users_email" not in existing_indexes:
        op.create_index("ix_users_email", "users", ["email"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
