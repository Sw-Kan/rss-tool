"""F3 自动化：当 → 如果（可多个，and/or）→ 则。

两种求值时机：
1. **新条目触发**：抓取管线 upsert 之后，只对本次新增的文章逐用户匹配。
2. **定时触发**：`services/scheduler.py` 每分钟检查有没有到点的 schedule 规则，
   只处理「上次执行之后入库」的文章，避免每天把同一批再推一遍。

写权限：本模块不直接写 `user_item_state`，改状态一律经 `services/item_state.py`
（M7 的写入口），既满足 AGENTS.md §4，也不用复制一份写逻辑。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Article, AutomationRule, Feed, Subscription, User
from . import integrations, item_state

logger = logging.getLogger("rss-tool.automation")

TRIGGER_KINDS: dict[str, str] = {
    "item_arrived": "article",
    "video_arrived": "video",
    "picture_arrived": "picture",
}

# 定时规则在没有 last_run_at 时的回看窗口
SCHEDULE_LOOKBACK = timedelta(hours=24)
# 一次定时评估最多看多少篇，避免规则写错时把整库翻一遍
SCHEDULE_MAX_ARTICLES = 200
TRUTHY = {"true", "1", "yes", "on"}


@dataclass(slots=True)
class RuleHit:
    rule_id: str
    rule_name: str
    action: str
    detail: str = ""


def _as_bool(value: str) -> bool:
    return value.strip().lower() in TRUTHY


def condition_matches(condition: dict, article: Article, feed_title: str, state: dict) -> bool:
    field = condition.get("field")
    op = condition.get("op")
    needle = str(condition.get("value") or "").strip()

    if field == "word_count":
        try:
            threshold = int(needle)
        except (TypeError, ValueError):
            return False
        return {
            "gt": article.word_count > threshold,
            "lt": article.word_count < threshold,
            "eq": article.word_count == threshold,
        }.get(str(op), False)

    if field in ("favorite", "read"):
        if op != "eq":
            return False
        return bool(state.get(field)) is _as_bool(needle)

    if field == "kind":
        return op == "eq" and article.kind == needle

    values = {
        "title": article.title or "",
        "channel": article.channel_name or feed_title,
        "feed": feed_title,
    }
    haystack = values.get(str(field), "").lower()
    if not needle:
        return False
    target = needle.lower()
    if op == "contains":
        return target in haystack
    if op == "eq":
        return haystack == target
    return False


def rule_matches(
    rule: AutomationRule,
    article: Article,
    feed_title: str,
    state: dict | None = None,
) -> bool:
    conditions = rule.conditions or []
    if not conditions:
        return False

    results = [condition_matches(c, article, feed_title, state or {}) for c in conditions]
    return any(results) if rule.join == "or" else all(results)


def trigger_matches(rule: AutomationRule, article: Article) -> bool:
    expected = TRIGGER_KINDS.get(rule.trigger)
    if expected is None:
        return False  # schedule 由定时任务单独处理
    return article.kind == expected


async def apply_to_article(
    db: Session,
    user: User,
    article: Article,
    feed_title: str,
    *,
    pushes_left: dict[str, int],
    only_rule_ids: set[str] | None = None,
    for_schedule: bool = False,
) -> list[RuleHit]:
    rules = list(
        db.scalars(
            select(AutomationRule)
            .where(AutomationRule.user_id == user.id, AutomationRule.enabled.is_(True))
            .order_by(AutomationRule.position, AutomationRule.created_at)
        )
    )

    state = {
        "favorite": item_state.is_favorite(db, user.id, article.id),
        "read": item_state.is_read(db, user.id, article.id),
    }

    hits: list[RuleHit] = []
    for rule in rules:
        if only_rule_ids is not None and rule.id not in only_rule_ids:
            continue
        if for_schedule != (rule.trigger == "schedule"):
            continue
        if not for_schedule and not trigger_matches(rule, article):
            continue
        if not rule_matches(rule, article, feed_title, state):
            continue

        action = rule.action or {}
        kind = action.get("type")
        try:
            applied, detail = await _apply_action(db, user, article, feed_title, kind, pushes_left)
        except integrations.IntegrationError as exc:
            logger.info("automation: 规则「%s」动作失败：%s", rule.name, exc)
            continue
        except Exception:
            logger.exception("automation: 规则「%s」动作异常", rule.name)
            continue

        if not applied:
            logger.info("automation: 规则「%s」跳过：%s", rule.name, detail)
            continue
        hits.append(RuleHit(rule.id, rule.name, str(kind), detail))

    return hits


async def _apply_action(
    db: Session,
    user: User,
    article: Article,
    feed_title: str,
    kind: str | None,
    pushes_left: dict[str, int],
) -> tuple[bool, str]:
    """返回 (是否真的执行了动作, 说明文案)。"""
    if kind in ("favorite", "mark_read", "mark_unread"):
        item_state.set_state(
            db,
            user.id,
            article.id,
            is_favorite=True if kind == "favorite" else None,
            is_read=True if kind == "mark_read" else (False if kind == "mark_unread" else None),
        )
        return True, ""

    if kind is None:
        return False, "规则没有配置动作"

    if pushes_left.get(kind, 0) <= 0:
        return False, "本次已达推送上限"

    if not integrations.is_enabled(db, user.id, kind):
        raise integrations.IntegrationError(f"{kind} 集成未启用或未配置")

    config = integrations.get_config(db, user.id, kind)
    if kind == "feishu":
        await integrations.push_feishu(config, article, feed_title)
    elif kind == "obsidian":
        path = integrations.save_to_obsidian(config, article, feed_title)
        pushes_left[kind] -= 1
        return True, f"已写入 {path.name}"
    elif kind == "custom_export":
        await integrations.push_custom(config, article, feed_title)
    else:
        raise integrations.IntegrationError(f"未知动作：{kind}")

    pushes_left[kind] -= 1
    return True, ""


async def run_for_new_articles(db: Session, feed_id: str, article_ids: list[str]) -> int:
    """供抓取管线在 upsert 之后调用。返回执行的规则动作数。"""
    if not article_ids:
        return 0

    feed = db.get(Feed, feed_id)
    if feed is None:
        return 0

    subscriptions = list(db.scalars(select(Subscription).where(Subscription.feed_id == feed_id)))
    if not subscriptions:
        return 0

    articles = list(db.scalars(select(Article).where(Article.id.in_(article_ids))))
    applied = 0

    for subscription in subscriptions:
        user = db.get(User, subscription.user_id)
        if user is None:
            continue
        feed_title = subscription.custom_title or feed.title or feed.url
        pushes_left = {kind: integrations.MAX_PUSH_PER_RUN for kind in integrations.KINDS}
        for article in articles:
            hits = await apply_to_article(db, user, article, feed_title, pushes_left=pushes_left)
            applied += len(hits)

    return applied


def due_schedule_rules(db: Session, now: datetime | None = None) -> list[AutomationRule]:
    """到点且今天还没跑过的 schedule 规则。"""
    moment = now or datetime.now()
    today = moment.strftime("%Y-%m-%d")
    hhmm = moment.strftime("%H:%M")

    rows = db.scalars(
        select(AutomationRule).where(
            AutomationRule.enabled.is_(True),
            AutomationRule.trigger == "schedule",
        )
    )
    due = []
    for rule in rows:
        if rule.schedule_time != hhmm:
            continue
        if rule.last_run_at is not None:
            last_local = rule.last_run_at.astimezone()
            if last_local.strftime("%Y-%m-%d") == today:
                continue
        due.append(rule)
    return due


async def run_scheduled_rules(db: Session, now: datetime | None = None) -> int:
    """执行到点的定时规则。返回执行的动作数。"""
    moment = now or datetime.now()
    applied = 0

    for rule in due_schedule_rules(db, moment):
        user = db.get(User, rule.user_id)
        if user is None:
            continue

        since = rule.last_run_at or (datetime.now(UTC) - SCHEDULE_LOOKBACK)
        candidates = _schedule_candidates(db, user.id, since)
        pushes_left = {kind: integrations.MAX_PUSH_PER_RUN for kind in integrations.KINDS}

        for article, feed_title in candidates:
            hits = await apply_to_article(
                db,
                user,
                article,
                feed_title,
                pushes_left=pushes_left,
                only_rule_ids={rule.id},
                for_schedule=True,
            )
            applied += len(hits)

        rule.last_run_at = datetime.now(UTC)
        db.commit()
        logger.info(
            "automation: 定时规则「%s」评估 %s 篇，动作 %s 次",
            rule.name,
            len(candidates),
            applied,
        )

    return applied


def _schedule_candidates(db: Session, user_id: str, since: datetime) -> list[tuple[Article, str]]:
    rows = db.execute(
        select(Article, Subscription.custom_title, Feed.title, Feed.url)
        .join(Subscription, Subscription.feed_id == Article.feed_id)
        .join(Feed, Feed.id == Article.feed_id)
        .where(Subscription.user_id == user_id, Article.fetched_at >= since)
        .order_by(Article.fetched_at.desc())
        .limit(SCHEDULE_MAX_ARTICLES)
    ).all()
    return [(article, custom or title or url) for article, custom, title, url in rows]
