"""add resumes table

Revision ID: c9a2f4d8e105
Revises: b7e4c1a9f203
Create Date: 2026-11-26 14:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9a2f4d8e105"
down_revision: str | None = "b7e4c1a9f203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resumes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("target_role", sa.String(length=128), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_format", sa.String(length=16), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("structured_json", sa.JSON(), nullable=False),
        sa.Column("ai_review_json", sa.JSON(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("synced_to_boss_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("resumes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_resumes_is_active"), ["is_active"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("resumes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_resumes_is_active"))

    op.drop_table("resumes")
