"""F3 自动化：规则 CRUD、条件匹配、动作落地、与抓取管线的衔接。"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Article, AutomationRule, User, UserItemState
from app.services import automation, extract, feed_fetch, refresh
from tests.factories import RSS_20, make_feed

FEISHU = "https://open.feishu.cn/open-apis/bot/v2/hook/abc"
PAGE = "<html><body><article>" + "<p>真正的正文内容。</p>" * 40 + "</article></body></html>"


@pytest.fixture(autouse=True)
def allow_fake_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feed_fetch, "check_url_allowed", lambda url: [])


# ---------- 规则 CRUD ----------


def test_rule_crud(auth_client: TestClient) -> None:
    created = auth_client.post(
        "/api/automation/rules",
        json={
            "name": "Rust 文章自动收藏",
            "trigger": "item_arrived",
            "conditions": [{"field": "title", "op": "contains", "value": "Rust"}],
            "action": {"type": "favorite"},
        },
    )
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["name"] == "Rust 文章自动收藏"
    assert rule["enabled"] is True
    assert rule["conditions"][0]["value"] == "Rust"

    patched = auth_client.patch(
        f"/api/automation/rules/{rule['id']}", json={"enabled": False}
    ).json()
    assert patched["enabled"] is False

    assert auth_client.get("/api/automation/rules").json() == [patched]
    assert auth_client.delete(f"/api/automation/rules/{rule['id']}").status_code == 204
    assert auth_client.get("/api/automation/rules").json() == []


def test_rule_defaults(auth_client: TestClient) -> None:
    rule = auth_client.post("/api/automation/rules", json={}).json()
    assert rule["name"] == "新规则"
    assert rule["trigger"] == "item_arrived"
    assert rule["action"]["type"] == "favorite"


@pytest.mark.parametrize(
    "payload",
    [
        {"trigger": "on_sunrise"},
        {"conditions": [{"field": "mood", "op": "contains", "value": "x"}]},
        {"conditions": [{"field": "title", "op": "gt", "value": "1"}]},
        {"trigger": "schedule", "schedule_time": "25:00"},
        {"action": {"type": "explode"}},
    ],
)
def test_rule_rejects_unknown_values(auth_client: TestClient, payload: dict) -> None:
    assert auth_client.post("/api/automation/rules", json=payload).status_code == 422


def test_rules_are_isolated_between_users(auth_client: TestClient) -> None:
    rule = auth_client.post("/api/automation/rules", json={"name": "我的"}).json()

    other = TestClient(auth_client.app)
    other.post(
        "/api/auth/register", json={"username": "b", "email": "b@x.com", "password": "12345678"}
    )
    assert other.get("/api/automation/rules").json() == []
    assert other.patch(f"/api/automation/rules/{rule['id']}", json={}).status_code == 404
    assert other.delete(f"/api/automation/rules/{rule['id']}").status_code == 404


# ---------- 条件匹配 ----------


def _article(kind: str = "article", **overrides: object) -> Article:
    article = Article(title="Rust 1.85 发布", kind=kind, word_count=3400, feed_id="f")
    for key, value in overrides.items():
        setattr(article, key, value)
    return article


def _rule(trigger: str, field: str, op: str, value: str) -> AutomationRule:
    return AutomationRule(
        user_id="u",
        trigger=trigger,
        join="and",
        conditions=[{"field": field, "op": op, "value": value}],
        action={"type": "favorite"},
    )


def matches(rule: AutomationRule, article: Article, feed_title: str = "少数派") -> bool:
    """完整判定 = 触发类型命中 + 条件命中（定时触发不走 trigger_matches）。"""
    return automation.trigger_matches(rule, article) and automation.rule_matches(
        rule, article, feed_title
    )


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (_rule("item_arrived", "title", "contains", "rust"), True),
        (_rule("item_arrived", "title", "contains", "python"), False),
        (_rule("item_arrived", "title", "eq", "Rust 1.85 发布"), True),
        (_rule("item_arrived", "word_count", "gt", "3000"), True),
        (_rule("item_arrived", "word_count", "lt", "3000"), False),
        (_rule("item_arrived", "kind", "eq", "article"), True),
        (_rule("item_arrived", "kind", "eq", "video"), False),
        # 触发类型不匹配：视频规则不该被文章命中
        (_rule("video_arrived", "title", "contains", "rust"), False),
    ],
)
def test_rule_matches(rule: AutomationRule, expected: bool) -> None:
    assert matches(rule, _article()) is expected


def test_schedule_trigger_is_not_a_kind_trigger() -> None:
    """schedule 由定时任务单独处理，不该被「新文章到达」这条路命中。"""
    rule = _rule("schedule", "title", "contains", "rust")
    assert automation.trigger_matches(rule, _article()) is False


def test_or_join_matches_when_any_condition_holds() -> None:
    rule = AutomationRule(
        user_id="u",
        trigger="item_arrived",
        join="or",
        conditions=[
            {"field": "title", "op": "contains", "value": "python"},
            {"field": "word_count", "op": "gt", "value": "3000"},
        ],
        action={"type": "favorite"},
    )
    assert automation.rule_matches(rule, _article(), "少数派") is True


def test_and_join_needs_all_conditions() -> None:
    rule = AutomationRule(
        user_id="u",
        trigger="item_arrived",
        join="and",
        conditions=[
            {"field": "title", "op": "contains", "value": "rust"},
            {"field": "word_count", "op": "gt", "value": "99999"},
        ],
        action={"type": "favorite"},
    )
    assert automation.rule_matches(rule, _article(), "少数派") is False


def test_rule_without_conditions_never_matches() -> None:
    rule = AutomationRule(
        user_id="u", trigger="item_arrived", conditions=[], action={"type": "favorite"}
    )
    assert automation.rule_matches(rule, _article(), "少数派") is False


@pytest.mark.parametrize(
    ("field", "value", "state", "expected"),
    [
        ("favorite", "true", {"favorite": True, "read": False}, True),
        ("favorite", "true", {"favorite": False, "read": False}, False),
        ("favorite", "false", {"favorite": False, "read": False}, True),
        ("read", "true", {"favorite": False, "read": True}, True),
        ("read", "false", {"favorite": True, "read": False}, True),
        # 非法值一律不命中
        ("favorite", "maybe", {"favorite": True, "read": False}, False),
    ],
)
def test_reading_state_conditions(field: str, value: str, state: dict, expected: bool) -> None:
    condition = {"field": field, "op": "eq", "value": value}
    assert automation.condition_matches(condition, _article(), "少数派", state) is expected


# ---------- 动作落地 ----------


def _seed(db: Session) -> tuple[User, Article, str]:
    user = db.query(User).order_by(User.created_at).first()
    assert user is not None
    feed = make_feed(db, "少数派", url="https://sspai.com/feed")
    from tests.factories import add_article, subscribe

    subscribe(db, user, feed)
    article = add_article(db, feed, guid="g1", title="Rust 1.85 发布")
    db.commit()
    return user, article, feed.id


@pytest.mark.asyncio
async def test_favorite_action_writes_state(auth_client: TestClient, db: Session) -> None:
    _ = auth_client
    user, article, feed_id = _seed(db)
    db.add(
        AutomationRule(
            user_id=user.id,
            name="收藏 Rust",
            trigger="item_arrived",
            conditions=[{"field": "title", "op": "contains", "value": "rust"}],
            action={"type": "favorite"},
            position=1,
        )
    )
    db.commit()

    applied = await automation.run_for_new_articles(db, feed_id, [article.id])
    assert applied == 1

    state = db.query(UserItemState).filter_by(user_id=user.id, article_id=article.id).one()
    assert state.is_favorite is True
    assert state.is_read is False


@pytest.mark.asyncio
async def test_disabled_rule_is_skipped(auth_client: TestClient, db: Session) -> None:
    _ = auth_client
    user, article, feed_id = _seed(db)
    db.add(
        AutomationRule(
            user_id=user.id,
            name="关掉的规则",
            enabled=False,
            trigger="item_arrived",
            conditions=[{"field": "title", "op": "contains", "value": "rust"}],
            action={"type": "favorite"},
        )
    )
    db.commit()

    assert await automation.run_for_new_articles(db, feed_id, [article.id]) == 0
    assert db.query(UserItemState).count() == 0


@pytest.mark.asyncio
async def test_feishu_action_pushes(auth_client: TestClient, db: Session) -> None:
    auth_client.put("/api/integrations/feishu", json={"feishu": {"webhook_url": FEISHU}})
    user, article, feed_id = _seed(db)
    db.add(
        AutomationRule(
            user_id=user.id,
            name="推送飞书",
            trigger="item_arrived",
            conditions=[{"field": "title", "op": "contains", "value": "rust"}],
            action={"type": "feishu"},
        )
    )
    db.commit()

    with respx.mock:
        route = respx.post(FEISHU).mock(return_value=httpx.Response(200, json={"code": 0}))
        applied = await automation.run_for_new_articles(db, feed_id, [article.id])

    assert applied == 1
    payload = json.loads(route.calls[0].request.content)
    assert "Rust 1.85 发布" in payload["content"]["text"]


@pytest.mark.asyncio
async def test_feishu_action_without_config_is_reported_not_raised(
    auth_client: TestClient, db: Session
) -> None:
    _ = auth_client
    user, article, feed_id = _seed(db)
    db.add(
        AutomationRule(
            user_id=user.id,
            name="没配集成",
            trigger="item_arrived",
            conditions=[{"field": "title", "op": "contains", "value": "rust"}],
            action={"type": "feishu"},
        )
    )
    db.commit()

    # 集成没配好 → 记日志跳过：既不算命中，也不抛异常
    hits = await automation.apply_to_article(db, user, article, "少数派", pushes_left={"feishu": 5})
    assert hits == []


@pytest.mark.asyncio
async def test_push_is_capped_per_run(auth_client: TestClient, db: Session) -> None:
    auth_client.put("/api/integrations/feishu", json={"feishu": {"webhook_url": FEISHU}})
    user, _article, feed_id = _seed(db)
    db.add(
        AutomationRule(
            user_id=user.id,
            name="推送飞书",
            trigger="item_arrived",
            conditions=[{"field": "title", "op": "contains", "value": "rust"}],
            action={"type": "feishu"},
        )
    )
    # 再补 8 篇，凑够 9 篇一次性触发
    from tests.factories import add_article

    feed = db.get(Article, _article.id).feed  # type: ignore[union-attr]
    ids = [add_article(db, feed, guid=f"cap{i}", title=f"Rust 文章 {i}").id for i in range(8)]
    ids.append(_article.id)
    db.commit()

    with respx.mock:
        route = respx.post(FEISHU).mock(return_value=httpx.Response(200, json={"code": 0}))
        await automation.run_for_new_articles(db, feed_id, ids)

    assert route.call_count == automation.integrations.MAX_PUSH_PER_RUN


@pytest.mark.asyncio
async def test_rules_run_in_order_and_all_matching_ones_apply(
    auth_client: TestClient, db: Session
) -> None:
    _ = auth_client
    user, article, feed_id = _seed(db)
    for position, (name, action) in enumerate(
        [("先收藏", "favorite"), ("再标记已读", "mark_read")], start=1
    ):
        db.add(
            AutomationRule(
                user_id=user.id,
                name=name,
                trigger="item_arrived",
                conditions=[{"field": "title", "op": "contains", "value": "rust"}],
                action={"type": action},
                position=position,
            )
        )
    db.commit()

    applied = await automation.run_for_new_articles(db, feed_id, [article.id])
    assert applied == 2
    state = db.query(UserItemState).filter_by(user_id=user.id, article_id=article.id).one()
    assert (state.is_favorite, state.is_read) == (True, True)


@pytest.mark.asyncio
async def test_only_new_articles_are_evaluated(auth_client: TestClient, db: Session) -> None:
    _ = auth_client
    user, _article, feed_id = _seed(db)
    db.add(
        AutomationRule(
            user_id=user.id,
            name="收藏 Rust",
            trigger="item_arrived",
            conditions=[{"field": "title", "op": "contains", "value": "rust"}],
            action={"type": "favorite"},
        )
    )
    db.commit()

    assert await automation.run_for_new_articles(db, feed_id, []) == 0


# ---------- 与抓取管线的衔接 ----------


@pytest.mark.asyncio
async def test_refresh_triggers_automation_after_extraction(
    auth_client: TestClient, db: Session
) -> None:
    """「字数 > N」这类条件必须看到抽取后的字数，所以自动化要排在抽取之后。"""
    _ = auth_client
    user = db.query(User).order_by(User.created_at).first()
    assert user is not None
    feed = make_feed(db, "少数派", url="https://sspai.com/feed")
    from tests.factories import subscribe

    subscribe(db, user, feed)
    db.add(
        AutomationRule(
            user_id=user.id,
            name="长文收藏",
            trigger="item_arrived",
            conditions=[{"field": "word_count", "op": "gt", "value": "200"}],
            action={"type": "favorite"},
        )
    )
    db.commit()

    with respx.mock:
        respx.get("https://sspai.com/feed").mock(return_value=httpx.Response(200, content=RSS_20))
        # 只有第一篇是需要抽取的文章；第二/三篇分别是图片与视频
        respx.get("https://sspai.com/post/1").mock(
            return_value=httpx.Response(200, content=PAGE.encode())
        )
        result = await refresh.refresh_feed(db, feed)

    assert result.new_count == 3

    favorites = [
        state.article_id
        for state in db.query(UserItemState).filter_by(user_id=user.id, is_favorite=True)
    ]
    # RSS_20 第一篇正文很长（会被抽取），第三篇是视频、第二篇是图片 → 只有第一篇命中
    assert len(favorites) == 1

    with SessionLocal() as session:
        assert session.get(Article, favorites[0]).kind == "article"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_add_feed_does_not_run_automation(auth_client: TestClient, db: Session) -> None:
    """新增订阅不触发自动化，避免加一个源就瞬间打一堆推送。"""
    _ = auth_client
    user = db.query(User).order_by(User.created_at).first()
    assert user is not None
    db.add(
        AutomationRule(
            user_id=user.id,
            name="收藏全部",
            trigger="item_arrived",
            conditions=[{"field": "title", "op": "contains", "value": ""}],
            action={"type": "favorite"},
        )
    )
    db.commit()

    with respx.mock:
        respx.get("https://sspai.com/feed").mock(return_value=httpx.Response(200, content=RSS_20))
        created = auth_client.post("/api/feeds", json={"url": "https://sspai.com/feed"})

    assert created.status_code == 201
    assert db.query(UserItemState).count() == 0


def test_extract_pending_is_reachable_with_proxy_spec(db: Session) -> None:
    """抽取要能用当前代理配置（签名一致性）。"""
    import inspect

    signature = inspect.signature(extract.extract_pending)
    assert "spec" in signature.parameters


# ---------- 定时规则 ----------


def _add_schedule_rule(db: Session, user_id: str, hhmm: str, value: str = "rust") -> AutomationRule:
    rule = AutomationRule(
        user_id=user_id,
        name="每天推送",
        trigger="schedule",
        schedule_time=hhmm,
        join="and",
        conditions=[{"field": "title", "op": "contains", "value": value}],
        action={"type": "favorite"},
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def test_schedule_time_is_cleared_for_other_triggers(auth_client: TestClient) -> None:
    """非定时触发不该留着误导性的时间。"""
    created = auth_client.post(
        "/api/automation/rules",
        json={"trigger": "item_arrived", "schedule_time": "08:00"},
    ).json()
    assert created["schedule_time"] is None

    switched = auth_client.patch(
        f"/api/automation/rules/{created['id']}", json={"trigger": "schedule"}
    ).json()
    assert switched["schedule_time"] == "08:00"


def test_due_schedule_rules_only_fire_once_a_day(auth_client: TestClient, db: Session) -> None:
    from datetime import UTC, datetime

    _ = auth_client
    user, _article, _feed_id = _seed(db)
    now = datetime.now()
    rule = _add_schedule_rule(db, user.id, now.strftime("%H:%M"))

    due = automation.due_schedule_rules(db, now)
    assert [r.id for r in due] == [rule.id]

    rule.last_run_at = datetime.now(UTC)
    db.commit()
    assert automation.due_schedule_rules(db, now) == []


def test_schedule_rule_with_other_time_is_not_due(auth_client: TestClient, db: Session) -> None:
    from datetime import datetime

    _ = auth_client
    user, _article, _feed_id = _seed(db)
    now = datetime.now()
    _add_schedule_rule(db, user.id, "23:59" if now.strftime("%H:%M") != "23:59" else "00:00")
    assert automation.due_schedule_rules(db, now) == []


@pytest.mark.asyncio
async def test_run_scheduled_rules_applies_action_and_stamps_last_run(
    auth_client: TestClient, db: Session
) -> None:
    from datetime import datetime

    _ = auth_client
    user, article, _feed_id = _seed(db)
    now = datetime.now()
    rule = _add_schedule_rule(db, user.id, now.strftime("%H:%M"))

    applied = await automation.run_scheduled_rules(db, now)

    assert applied == 1
    db.refresh(rule)
    assert rule.last_run_at is not None
    state = db.query(UserItemState).filter_by(user_id=user.id, article_id=article.id).one()
    assert state.is_favorite is True

    # 同一天再跑一次不该重复执行
    assert await automation.run_scheduled_rules(db, now) == 0


@pytest.mark.asyncio
async def test_schedule_only_sees_articles_fetched_after_last_run(
    auth_client: TestClient, db: Session
) -> None:
    from datetime import UTC, datetime

    _ = auth_client
    user, _article, _feed_id = _seed(db)
    now = datetime.now()
    rule = _add_schedule_rule(db, user.id, now.strftime("%H:%M"))
    rule.last_run_at = datetime.now(UTC)
    db.commit()

    # 上一篇是 last_run_at 之前入库的 → 不该再被处理
    assert await automation.run_scheduled_rules(db, now) == 0
