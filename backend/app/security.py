"""密码哈希与 JWT。直接用 bcrypt，不引入 passlib。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from .config import get_settings

ALGORITHM = "HS256"
# bcrypt 只使用前 72 字节；超长密码在 schema 层已限制。
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(raw, password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.token_ttl_days)).timestamp()),
    }
    return jwt.encode(payload, settings.resolve_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> str | None:
    """返回 user_id；无效或过期返回 None。"""
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.resolve_secret_key(), algorithms=[ALGORITHM]
        )
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None
