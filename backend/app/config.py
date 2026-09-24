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
