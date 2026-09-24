"""用户 DTO 归一：拼出头像 URL，避免各路由重复。"""

from __future__ import annotations

from ..models import User
from ..schemas import UserOut

# 跳过登录时对外展示的占位邮箱
SKIP_EMAIL = "skip@local"
SKIP_DISPLAY_EMAIL = "example@example.com"


def public_user(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=SKIP_DISPLAY_EMAIL if user.email == SKIP_EMAIL else user.email,
        avatar_type="image" if user.avatar_type == "image" and user.avatar_path else "letter",
        avatar_color=user.avatar_color,
        avatar_url=f"/api/users/avatar/{user.avatar_path}" if user.avatar_path else None,
    )
