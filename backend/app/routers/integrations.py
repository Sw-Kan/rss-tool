"""F2 集成接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..deps import CurrentUser, DbSession
from ..schemas import (
    CustomExportConfig,
    FeishuConfig,
    IntegrationKind,
    IntegrationListOut,
    IntegrationOut,
    IntegrationPatch,
    IntegrationTestOut,
    ObsidianConfig,
    RsshubConfig,
)
from ..services import integrations

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

# 响应里每个 kind 只填自己那个字段（字段名与 kind 同名）
_MODELS = {
    "rsshub": RsshubConfig,
    "obsidian": ObsidianConfig,
    "feishu": FeishuConfig,
    "custom_export": CustomExportConfig,
}


def _out(kind: str, enabled: bool, config: dict, updated_at) -> IntegrationOut:  # noqa: ANN001
    model = _MODELS[kind]
    payload = {kind: model(**integrations.masked_config(kind, config))}
    return IntegrationOut(kind=kind, enabled=enabled, updated_at=updated_at, **payload)  # type: ignore[arg-type]


@router.get("", response_model=IntegrationListOut)
def list_integrations(user: CurrentUser, db: DbSession) -> IntegrationListOut:
    rows = integrations.list_rows(db, user.id)
    items: list[IntegrationOut] = []
    for kind in integrations.KINDS:
        row = rows.get(kind)
        config = integrations.get_config(db, user.id, kind)
        items.append(
            _out(kind, bool(row.enabled) if row else True, config, row.updated_at if row else None)
        )
    return IntegrationListOut(items=items)


@router.put("/{kind}", response_model=IntegrationOut)
def update_integration(
    kind: IntegrationKind, payload: IntegrationPatch, user: CurrentUser, db: DbSession
) -> IntegrationOut:
    incoming = getattr(payload, kind, None)
    config = incoming.model_dump() if incoming is not None else None

    try:
        row = integrations.upsert(db, user.id, kind, enabled=payload.enabled, config=config)
    except integrations.IntegrationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _out(kind, row.enabled, integrations.merged_config(row), row.updated_at)


@router.post("/rsshub/test", response_model=IntegrationTestOut)
async def test_rsshub(user: CurrentUser, db: DbSession) -> IntegrationTestOut:
    config = integrations.get_config(db, user.id, "rsshub")
    ok, message, latency = await integrations.test_rsshub(config)
    return IntegrationTestOut(ok=ok, message=message, latency_ms=latency)


@router.get("/custom_export/default-schema")
def default_schema() -> dict[str, str]:
    """新建自定义导出时给前端的默认模板。"""
    return {"schema_template": integrations.DEFAULT_SCHEMA}


@router.post("/custom_export/test", response_model=IntegrationTestOut)
async def test_custom_export(user: CurrentUser, db: DbSession) -> IntegrationTestOut:
    config = integrations.get_config(db, user.id, "custom_export")
    ok, message, latency = await integrations.test_custom_export(config)
    return IntegrationTestOut(ok=ok, message=message, latency_ms=latency)
