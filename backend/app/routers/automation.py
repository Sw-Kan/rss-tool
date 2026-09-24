"""F3 自动化接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..deps import CurrentUser, DbSession
from ..models import AutomationRule
from ..schemas import RuleCondition, RuleCreate, RuleOut, RulePatch

router = APIRouter(prefix="/api/automation", tags=["automation"])


def _out(row: AutomationRule) -> RuleOut:
    condition = row.condition or {}
    action = row.action or {}
    return RuleOut(
        id=row.id,
        name=row.name,
        enabled=row.enabled,
        position=row.position,
        trigger=row.trigger,  # type: ignore[arg-type]
        condition=RuleCondition(
            field=condition.get("field", "title"),
            op=condition.get("op", "contains"),
            value=str(condition.get("value") or ""),
        ),
        action={"type": action.get("type", "favorite")},  # type: ignore[arg-type]
    )


def _owned(db: DbSession, user_id: str, rule_id: str) -> AutomationRule:
    row = db.get(AutomationRule, rule_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="规则不存在")
    return row


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
        condition=payload.condition.model_dump(),
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
    if payload.condition is not None:
        row.condition = payload.condition.model_dump()
    if payload.action is not None:
        row.action = payload.action.model_dump()

    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: str, user: CurrentUser, db: DbSession) -> None:
    db.delete(_owned(db, user.id, rule_id))
    db.commit()
