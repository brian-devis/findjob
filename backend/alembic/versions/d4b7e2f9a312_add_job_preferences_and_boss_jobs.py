"""add job_preferences and boss_jobs tables

Revision ID: d4b7e2f9a312
Revises: c9a2f4d8e105
Create Date: 2026-11-26 15:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4b7e2f9a312"
down_revision: str | None = "c9a2f4d8e105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("cities", sa.JSON(), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("exclude_companies", sa.JSON(), nullable=False),
        sa.Column("exclude_keywords", sa.JSON(), nullable=False),
        sa.Column("auto_apply_enabled", sa.Boolean(), nullable=False),
        sa.Column("auto_apply_min_score", sa.Integer(), nullable=False),
        sa.Column("daily_apply_limit", sa.Integer(), nullable=False),
        sa.Column("apply_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("greeting_template", sa.Text(), nullable=True),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "boss_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("boss_job_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("salary", sa.String(length=64), nullable=True),
        sa.Column("experience", sa.String(length=64), nullable=True),
        sa.Column("education", sa.String(length=64), nullable=True),
        sa.Column("recruiter", sa.String(length=128), nullable=True),
        sa.Column("job_url", sa.String(length=512), nullable=True),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=True),
        sa.Column("match_reason", sa.Text(), nullable=True),
        sa.Column("ai_greeting", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=True),
        sa.Column("apply_task_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("boss_jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_boss_jobs_boss_job_id"), ["boss_job_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_boss_jobs_company"), ["company"], unique=False)
        batch_op.create_index(batch_op.f("ix_boss_jobs_match_score"), ["match_score"], unique=False)
        batch_op.create_index(batch_op.f("ix_boss_jobs_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("boss_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_boss_jobs_status"))
        batch_op.drop_index(batch_op.f("ix_boss_jobs_match_score"))
        batch_op.drop_index(batch_op.f("ix_boss_jobs_company"))
        batch_op.drop_index(batch_op.f("ix_boss_jobs_boss_job_id"))

    op.drop_table("boss_jobs")
    op.drop_table("job_preferences")
