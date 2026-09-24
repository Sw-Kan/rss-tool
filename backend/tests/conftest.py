"""测试夹具。必须在 import app 之前改环境变量，保证用独立的临时库。"""

from __future__ import annotations

import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="rss-tool-test-")
os.environ["DATA_DIR"] = _TMP
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-" + "a" * 32
os.environ["ALLOW_PRIVATE_FETCH"] = "false"
os.environ["REFRESH_DEFAULT_MINUTES"] = "60"
# 重试退避在测试里没意义，设 0 免得每条重试用例白等 3 秒
os.environ["AI_RETRY_BACKOFF_SECONDS"] = "0"

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def fresh_db() -> Iterator[None]:
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Iterator[TestClient]:
    # 不用 with 上下文：跳过 lifespan（避免每个用例都起调度器）
    yield TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    response = client.post("/api/auth/skip")
    assert response.status_code == 200
    return client
