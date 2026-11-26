"""求职偏好与岗位漏斗数据访问。"""
from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import BossJobStatus
from app.core.time import utcnow
from app.models.job import BossJob, JobPreference


class JobPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_default(self) -> JobPreference:
        result = await self._session.execute(
            select(JobPreference).where(JobPreference.id == 1)
        )
        pref = result.scalar_one_or_none()
        if pref is not None:
            return pref

        result = await self._session.execute(
            select(JobPreference).order_by(JobPreference.id.asc()).limit(1)
        )
        pref = result.scalar_one_or_none()
        if pref is not None:
            return pref

        pref = JobPreference(
            id=1,
            keywords=[],
            cities=[],
            exclude_companies=[],
            exclude_keywords=[],
            auto_apply_enabled=False,
            auto_apply_min_score=80,
            daily_apply_limit=30,
            apply_interval_seconds=45,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(pref)
                await self._session.flush()
            return pref
        except IntegrityError:
            retry = await self._session.execute(
                select(JobPreference).order_by(JobPreference.id.asc()).limit(1)
            )
            existing = retry.scalar_one()
            return existing


class BossJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, job_id: int) -> BossJob | None:
        result = await self._session.execute(select(BossJob).where(BossJob.id == job_id))
        return result.scalar_one_or_none()

    async def get_by_boss_job_id(self, boss_job_id: str) -> BossJob | None:
        result = await self._session.execute(
            select(BossJob).where(BossJob.boss_job_id == boss_job_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
        min_score: int | None = None,
    ) -> list[BossJob]:
        stmt = select(BossJob)
        if status and status != "all":
            stmt = stmt.where(BossJob.status == status)
        if min_score is not None:
            stmt = stmt.where(BossJob.match_score >= min_score)
        stmt = (
            stmt.order_by(
                BossJob.match_score.is_(None),
                BossJob.match_score.desc(),
                BossJob.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, status: str | None = None, min_score: int | None = None) -> int:
        stmt = select(func.count()).select_from(BossJob)
        if status and status != "all":
            stmt = stmt.where(BossJob.status == status)
        if min_score is not None:
            stmt = stmt.where(BossJob.match_score >= min_score)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_applied_today(self) -> int:
        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(func.count())
            .select_from(BossJob)
            .where(
                or_(
                    and_(
                        BossJob.status == BossJobStatus.APPLIED.value,
                        BossJob.applied_at >= today_start,
                    ),
                    and_(
                        BossJob.status == BossJobStatus.APPLYING.value,
                        BossJob.updated_at >= today_start,
                    ),
                )
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_auto_apply_candidates(self, *, min_score: int, limit: int) -> list[BossJob]:
        stmt = (
            select(BossJob)
            .where(
                BossJob.status == BossJobStatus.SCORED.value,
                BossJob.match_score.is_not(None),
                BossJob.match_score >= min_score,
            )
            .order_by(BossJob.match_score.desc(), BossJob.id.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_unscored(self, *, limit: int) -> list[BossJob]:
        stmt = (
            select(BossJob)
            .where(BossJob.status == BossJobStatus.DISCOVERED.value)
            .order_by(BossJob.id.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def status_counts(self) -> dict[str, int]:
        stmt = select(BossJob.status, func.count()).group_by(BossJob.status)
        result = await self._session.execute(stmt)
        return {str(status): int(cnt) for status, cnt in result.all()}

    async def count_high_score_ready(self, *, min_score: int) -> int:
        stmt = (
            select(func.count())
            .select_from(BossJob)
            .where(
                BossJob.status == BossJobStatus.SCORED.value,
                BossJob.match_score.is_not(None),
                BossJob.match_score >= min_score,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
