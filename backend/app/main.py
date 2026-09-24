"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import scheduler
from .config import get_settings
from .db import init_db
from .routers import (
    ai,
    auth,
    automation,
    data,
    feeds,
    folders,
    integrations,
    items,
    media,
    opml,
    proxy,
    users,
)
from .routers import settings as settings_router
from .schemas import HealthOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="rss-tool", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(folders.router)
app.include_router(feeds.router)
app.include_router(items.router)
app.include_router(settings_router.router)
app.include_router(opml.router)
app.include_router(data.router)
app.include_router(ai.router)
app.include_router(integrations.router)
app.include_router(automation.router)
app.include_router(proxy.router)
app.include_router(media.router)


@app.get("/api/health", response_model=HealthOut, tags=["health"])
def health() -> HealthOut:
    return HealthOut(status="ok", scheduler_running=scheduler.is_running())
