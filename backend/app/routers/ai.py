"""F1 AI 助手：供应商配置、用量、总结与标题翻译。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession, SettingsRow
from ..models import AiProvider, AiResult, Article, Subscription
from ..schemas import (
    AiArticleIn,
    AiConfigOut,
    AiKind,
    AiProviderCreate,
    AiProviderOut,
    AiProviderPatch,
    AiResultOut,
    AiResultsOut,
    AiUsageOut,
)
from ..services import ai

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------- 供应商配置 ----------


def _provider_out(provider: AiProvider) -> AiProviderOut:
    return AiProviderOut(
        id=provider.id,
        label=provider.label,
        protocol=provider.protocol,  # type: ignore[arg-type]
        base_url=provider.base_url,
        model=provider.model,
        enabled=provider.enabled,
        position=provider.position,
        has_key=bool(provider.api_key),
        api_key_hint=ai.mask_key(provider.api_key),
    )


def _list_providers(db: Session, user_id: str) -> list[AiProvider]:
    return list(
        db.scalars(
            select(AiProvider)
            .where(AiProvider.user_id == user_id)
            .order_by(AiProvider.position, AiProvider.created_at)
        )
    )


def _owned(db: Session, user_id: str, provider_id: str) -> AiProvider:
    provider = db.get(AiProvider, provider_id)
    if provider is None or provider.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    return provider


@router.get("/config", response_model=AiConfigOut)
def read_config(user: CurrentUser, db: DbSession, settings: SettingsRow) -> AiConfigOut:
    return AiConfigOut(
        providers=[_provider_out(p) for p in _list_providers(db, user.id)],
        token_limit=settings.ai_token_limit,
    )


@router.get("/presets")
def read_presets() -> list[dict[str, str]]:
    """预设列表，供前端「添加供应商」菜单使用。"""
    return [
        {"key": p.key, "label": p.label, "base_url": p.base_url, "model": p.model}
        for p in ai.PRESETS
    ]


@router.post("/providers", response_model=AiProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(payload: AiProviderCreate, user: CurrentUser, db: DbSession) -> AiProviderOut:
    preset = ai.PRESETS_BY_KEY.get(payload.preset)
    if preset is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="未知的供应商预设")

    last = db.scalar(select(func.max(AiProvider.position)).where(AiProvider.user_id == user.id))
    provider = AiProvider(
        user_id=user.id,
        label=preset.label,
        protocol=preset.protocol,
        base_url=preset.base_url,
        model=preset.model,
        position=(last or 0) + 1,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return _provider_out(provider)


@router.patch("/providers/{provider_id}", response_model=AiProviderOut)
def patch_provider(
    provider_id: str, payload: AiProviderPatch, user: CurrentUser, db: DbSession
) -> AiProviderOut:
    provider = _owned(db, user.id, provider_id)

    if payload.label is not None:
        label = payload.label.strip()
        if not label:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="名称不能为空")
        provider.label = label
    if payload.base_url is not None:
        provider.base_url = payload.base_url.strip()
    if payload.model is not None:
        provider.model = payload.model.strip()
    if payload.enabled is not None:
        provider.enabled = payload.enabled
    if payload.clear_key:
        provider.api_key = ""
    elif payload.api_key:
        # 空串视为「不改」：前端只回传掩码提示，不能把 key 抹掉
        provider.api_key = payload.api_key.strip()

    db.commit()
    db.refresh(provider)
    return _provider_out(provider)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider_id: str, user: CurrentUser, db: DbSession) -> None:
    db.delete(_owned(db, user.id, provider_id))
    db.commit()


# ---------- 用量 ----------


@router.get("/usage", response_model=AiUsageOut)
def read_usage(user: CurrentUser, db: DbSession, settings: SettingsRow) -> AiUsageOut:
    return AiUsageOut(**ai.usage_summary(db, user.id, settings.ai_token_limit))


# ---------- 结果读 / 生成 ----------


@router.get("/results", response_model=AiResultsOut)
def read_results(article_id: str, user: CurrentUser, db: DbSession) -> AiResultsOut:
    """读已有结果（不触发上游），供打开文章时回填。"""
    _require_visible(db, user.id, article_id)
    summary = ai.cached_result(db, user.id, article_id, ai.SUMMARY)
    translation = ai.cached_result(db, user.id, article_id, ai.TITLE_TRANSLATION)
    return AiResultsOut(
        summary=_result_out(summary) if summary else None,
        title_translation=_result_out(translation) if translation else None,
    )


@router.post("/generate", response_model=AiResultOut)
async def generate(
    payload: AiArticleIn,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsRow,
    kind: AiKind = Query(...),
) -> AiResultOut:
    """生成（命中缓存则直接返回）。kind=summary 总结，kind=title_translation 标题翻译。"""
    _require_visible(db, user.id, payload.article_id)
    article = db.get(Article, payload.article_id)
    assert article is not None

    try:
        row, cached = await ai.run(db, user, article, kind, settings.ai_token_limit)
    except ai.AiLimitError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except ai.AiConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ai.AiError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return _result_out(row, cached=cached)


def _result_out(row: AiResult, *, cached: bool = True) -> AiResultOut:
    return AiResultOut(
        kind=row.kind,  # type: ignore[arg-type]
        content=row.content,
        model=row.model,
        cached=cached,
        tokens_in=row.tokens_in,
        tokens_out=row.tokens_out,
        created_at=row.created_at,
    )


def _require_visible(db: Session, user_id: str, article_id: str) -> None:
    visible = db.scalar(
        select(Article.id)
        .join(Subscription, Subscription.feed_id == Article.feed_id)
        .where(Article.id == article_id, Subscription.user_id == user_id)
        .limit(1)
    )
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文章不存在")
