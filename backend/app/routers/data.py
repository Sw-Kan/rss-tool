"""M10 数据导出与「清空本地数据」。

清空是单实例级操作：设计稿的文案是「删除本机全部账户、订阅与阅读记录」，
因此它不按用户维度，而是重置整个本地实例（保留当前会话无效，调用方需自行跳登录页）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, status
from sqlalchemy import delete

from ..config import get_settings
from ..deps import CurrentUser, DbSession
from ..models import (
    Article,
    Feed,
    Folder,
    Subscription,
    User,
    UserItemState,
    UserSettings,
)

router = APIRouter(prefix="/api/data", tags=["data"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_local_data(user: CurrentUser, db: DbSession) -> None:
    """清空本机全部订阅、文章、阅读记录与账号。"""
    _ = user  # 仅用于鉴权：必须已登录才能触发
    for model in (
        UserItemState,
        Article,
        Subscription,
        Feed,
        Folder,
        UserSettings,
        User,
    ):
        db.execute(delete(model))
    db.commit()
    _clear_uploads()


def _clear_uploads() -> None:
    uploads: Path = get_settings().uploads_path
    if uploads.exists():
        shutil.rmtree(uploads, ignore_errors=True)
    uploads.mkdir(parents=True, exist_ok=True)
