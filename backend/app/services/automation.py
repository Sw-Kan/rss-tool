"""F3 自动化：当 → 如果 → 则。

评估点在抓取管线的 upsert 之后：一次刷新结束后拿到本次**新增**的文章，逐用户按
`position` 顺序匹配规则。命中后继续匹配后续规则（设计稿写明「命中后仍可继续」）。

写权限：本模块不直接写 `user_item_state`，改状态一律经 `services/item_state.py`
（M7 的写入口），这样既满足 AGENTS.md §4，也不用复制一份写逻辑。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

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

TEXT_FIELDS = ("title", "channel", "feed")


@dataclass(slots=True)
class RuleHit:
    rule_id: str
    rule_name: str
    action: str
    detail: str = ""


def rule_matches(rule: AutomationRule, article: Article, feed_title: str) -> bool:
    expected_kind = TRIGGER_KINDS.get(rule.trigger)
    if expected_kind is None or article.kind != expected_kind:
        return False

    condition = rule.condition or {}
    field = condition.get("field")
    op = condition.get("op")
    needle = str(condition.get("value") or "").strip()

    if field == "word_count":
        try:
            threshold = int(needle)
        except (TypeError, ValueError):
            return False
        if op == "gt":
            return article.word_count > threshold
        if op == "lt":
            return article.word_count < threshold
        if op == "eq":
            return article.word_count == threshold
        return False

    if field == "kind":
        return op == "eq" and article.kind == needle

    values: dict[str, str] = {
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


async def apply_to_article(
    db: Session,
    user: User,
    article: Article,
    feed_title: str,
    *,
    pushes_left: dict[str, int],
) -> list[RuleHit]:
    rules = list(
        db.scalars(
            select(AutomationRule)
            .where(AutomationRule.user_id == user.id, AutomationRule.enabled.is_(True))
            .order_by(AutomationRule.position, AutomationRule.created_at)
        )
    )

    hits: list[RuleHit] = []
    for rule in rules:
        if not rule_matches(rule, article, feed_title):
            continue

        action = rule.action or {}
        kind = action.get("type")
        try:
            applied, detail = await _apply_action(db, user, article, feed_title, kind, pushes_left)
        except integrations.IntegrationError as exc:
            # 集成没配好不该让整条规则链崩掉，记录后继续
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

    # 推送类动作：受 MAX_PUSH_PER_RUN 约束，且要求对应集成已启用
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
