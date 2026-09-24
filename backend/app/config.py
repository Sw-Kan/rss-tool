"""应用配置。环境变量见 .env.example。"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = ""
    database_url: str = ""
    data_dir: str = "./data"
    cors_origins: str = "http://localhost:5173"
    refresh_default_minutes: int = 60

    token_cookie_name: str = "rss_token"
    token_ttl_days: int = 30

    fetch_timeout_seconds: float = 15.0
    fetch_max_bytes: int = 5 * 1024 * 1024
    fetch_max_entries: int = 100
    fetch_user_agent: str = "rss-tool/0.1"
    # 允许抓取内网地址。默认关闭（SSRF 防护）；自建 RSSHub / 局域网 feed 需要打开。
    allow_private_fetch: bool = False

    # F5 全文抽取：feed 正文过短时去原网页抽正文
    extract_enabled: bool = True
    # 纯文本短于该字数才值得抓原网页
    extract_min_chars: int = 200
    # 每个源每轮刷新最多抽几篇，避免一次打上百个网页
    extract_max_per_refresh: int = 10
    extract_concurrency: int = 3
    extract_timeout_seconds: float = 12.0
    extract_max_bytes: int = 3 * 1024 * 1024

    # F1 AI 助手
    ai_timeout_seconds: float = 60.0

    # F6 媒体缓存
    media_cache_enabled: bool = True
    # 磁盘预算（MB），超出按 LRU 淘汰
    media_cache_max_mb: int = 512
    media_fetch_timeout_seconds: float = 10.0
    media_max_bytes: int = 10 * 1024 * 1024
    # 取图失败后的重试窗口（小时），期间不再重试
    media_retry_hours: int = 6

    @property
    def data_path(self) -> Path:
        return (BACKEND_DIR / self.data_dir).resolve()

    @property
    def uploads_path(self) -> Path:
        return self.data_path / "uploads"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_path / 'rss.db'}"

    def ensure_dirs(self) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.uploads_path.mkdir(parents=True, exist_ok=True)

    def resolve_secret_key(self) -> str:
        """显式配置优先；否则生成一次并落盘，保证重启后 cookie 依然有效。"""
        if self.secret_key:
            return self.secret_key
        self.ensure_dirs()
        key_file = self.data_path / "secret.key"
        if not key_file.exists():
            key_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
            key_file.chmod(0o600)
        return key_file.read_text(encoding="utf-8").strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
