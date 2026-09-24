"""F3 自动化接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..deps import CurrentUser, DbSession
from ..models import AutomationRule
from ..schemas import RuleCondition, RuleCreate, RuleOut, RulePatch

router = APIRouter(prefix="/api/automation", tags=["automation"])


def _out(row: AutomationRule) -> RuleOut:
    action = row.action or {}
    conditions = [
        RuleCondition(
            field=item.get("field", "title"),
            op=item.get("op", "contains"),
            value=str(item.get("value") or ""),
        )
        for item in (row.conditions or [])
        if isinstance(item, dict)
    ]
    return RuleOut(
        id=row.id,
        name=row.name,
        enabled=row.enabled,
        position=row.position,
        trigger=row.trigger,  # type: ignore[arg-type]
        schedule_time=row.schedule_time,
        join=row.join,  # type: ignore[arg-type]
        conditions=conditions or [RuleCondition(field="title", op="contains", value="")],
        action={"type": action.get("type", "favorite")},  # type: ignore[arg-type]
    )


def _owned(db: DbSession, user_id: str, rule_id: str) -> AutomationRule:
    row = db.get(AutomationRule, rule_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="规则不存在")
    return row


def _schedule_time(trigger: str, value: str | None) -> str | None:
    """只有定时触发才保留时间；其它触发一律清空，避免留下误导性的旧值。"""
    if trigger != "schedule":
        return None
    return value or "08:00"


@router.get("/rules", response_model=list[RuleOut])
def list_rules(user: CurrentUser, db: DbSession) -> list[RuleOut]:
    rows = db.scalars(
        select(AutomationRule)
        .where(AutomationRule.user_id == user.id)
        .order_by(AutomationRule.position, AutomationRule.created_at)
    )
    return [_out(row) for row in rows]


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(payload: RuleCreate, user: CurrentUser, db: DbSession) -> RuleOut:
    last = db.scalar(
        select(func.max(AutomationRule.position)).where(AutomationRule.user_id == user.id)
    )
    row = AutomationRule(
        user_id=user.id,
        name=payload.name.strip() or "新规则",
        trigger=payload.trigger,
        schedule_time=_schedule_time(payload.trigger, payload.schedule_time),
        join=payload.join,
        conditions=[c.model_dump() for c in payload.conditions],
        action=payload.action.model_dump(),
        position=(last or 0) + 1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def patch_rule(rule_id: str, payload: RulePatch, user: CurrentUser, db: DbSession) -> RuleOut:
    row = _owned(db, user.id, rule_id)

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="规则名不能为空")
        row.name = name
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.trigger is not None:
        row.trigger = payload.trigger
    if payload.schedule_time is not None or payload.trigger is not None:
        row.schedule_time = _schedule_time(row.trigger, payload.schedule_time or row.schedule_time)
    if payload.join is not None:
        row.join = payload.join
    if payload.conditions is not None:
        row.conditions = [c.model_dump() for c in payload.conditions]
    if payload.action is not None:
        row.action = payload.action.model_dump()

    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: str, user: CurrentUser, db: DbSession) -> None:
    db.delete(_owned(db, user.id, rule_id))
    db.commit()
