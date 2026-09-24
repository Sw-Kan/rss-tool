"""定时轮询：每个用户一个 job，间隔来自 user_settings。

手动刷新（M2 的刷新端点）与此互不干扰；两者都走同一条抓取管线。
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from .db import session_scope
from .models import Feed, Subscription, UserSettings
from .services import refresh

logger = logging.getLogger("rss-tool.scheduler")

_scheduler: AsyncIOScheduler | None = None


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    reschedule_all()


def shutdown() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def reschedule_all() -> None:
    with session_scope() as db:
        rows = list(db.scalars(select(UserSettings)))
    for row in rows:
        reschedule_user(row.user_id, row.auto_refresh_enabled, row.refresh_interval_minutes)


def reschedule_user(user_id: str, enabled: bool, interval_minutes: int) -> None:
    if _scheduler is None:
        return
    job_id = _job_id(user_id)
    existing = _scheduler.get_job(job_id)
    if not enabled:
        if existing:
            _scheduler.remove_job(job_id)
        return
    _scheduler.add_job(
        _run_user_refresh,
        trigger=IntervalTrigger(minutes=interval_minutes),
        args=[user_id],
        id=job_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    logger.info("scheduler: user %s 每 %s 分钟刷新", user_id, interval_minutes)


def _job_id(user_id: str) -> str:
    return f"refresh:{user_id}"


async def _run_user_refresh(user_id: str) -> None:
    try:
        with session_scope() as db:
            feeds = list(
                db.scalars(
                    select(Feed)
                    .join(Subscription, Subscription.feed_id == Feed.id)
                    .where(Subscription.user_id == user_id)
                    .distinct()
                )
            )
            if not feeds:
                return
            results = await refresh.refresh_feeds(db, feeds)
        failed = [r for r in results if r.status == "error"]
        logger.info(
            "scheduler: user %s 刷新 %s 源，新增 %s 篇，失败 %s",
            user_id,
            len(results),
            sum(r.new_count for r in results),
            len(failed),
        )
    except Exception:  # 后台任务不能让异常冒到事件循环
        logger.exception("scheduler: 用户 %s 定时刷新失败", user_id)
