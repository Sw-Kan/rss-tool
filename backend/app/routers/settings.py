"""M8 设置与偏好。"""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import CurrentUser, DbSession, SettingsRow
from ..scheduler import reschedule_user
from ..schemas import SettingsOut, SettingsPatch

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_out(row: SettingsRow) -> SettingsOut:
    return SettingsOut(
        theme=row.theme,  # type: ignore[arg-type]
        language=row.language,  # type: ignore[arg-type]
        auto_refresh_enabled=row.auto_refresh_enabled,
        refresh_interval_minutes=row.refresh_interval_minutes,
        text_style=row.text_style,  # type: ignore[arg-type]
        ai_token_limit=row.ai_token_limit,
    )


@router.get("", response_model=SettingsOut)
def read_settings(row: SettingsRow) -> SettingsOut:
    return _to_out(row)


@router.patch("", response_model=SettingsOut)
def patch_settings(
    payload: SettingsPatch, user: CurrentUser, db: DbSession, row: SettingsRow
) -> SettingsOut:
    if payload.theme is not None:
        row.theme = payload.theme
    if payload.auto_refresh_enabled is not None:
        row.auto_refresh_enabled = payload.auto_refresh_enabled
    if payload.refresh_interval_minutes is not None:
        row.refresh_interval_minutes = payload.refresh_interval_minutes
    if payload.text_style is not None:
        row.text_style = payload.text_style
    if payload.language is not None:
        row.language = payload.language
    if payload.ai_token_limit is not None:
        row.ai_token_limit = payload.ai_token_limit

    db.commit()
    db.refresh(row)
    # 间隔变更即时生效
    reschedule_user(user.id, row.auto_refresh_enabled, row.refresh_interval_minutes)
    return _to_out(row)
