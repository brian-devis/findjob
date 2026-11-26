"""add audit_logs table

Revision ID: b7e4c1a9f203
Revises: dacdf03f3fdf
Create Date: 2026-11-26 10:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4c1a9f203"
down_revision: str | None = "dacdf03f3fdf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_logs_ts"), ["ts"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_logs_actor"), ["actor"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_logs_action"), ["action"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_logs_action"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_actor"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_ts"))

    op.drop_table("audit_logs")
