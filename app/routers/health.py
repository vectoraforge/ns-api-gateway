import asyncio
import time
from typing import Callable, Awaitable

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse
from openai import AsyncOpenAI

from app.database import get_db

router = APIRouter()


class ReadinessCache:
    def __init__(self, ttl_seconds: int):
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._checked_at: float | None = None
        self._ok: bool | None = None
        self._error: str | None = None

    async def check(self, checker: Callable[[], Awaitable[None]]) -> tuple[bool, str | None]:
        async with self._lock:
            now = time.monotonic()
            if self._checked_at is not None and (now - self._checked_at) < self._ttl_seconds:
                return bool(self._ok), self._error

            try:
                await checker()
            except Exception as exc:
                self._ok = False
                self._error = str(exc)
            else:
                self._ok = True
                self._error = None

            self._checked_at = now
            return bool(self._ok), self._error


async def _probe_llm(model_name: str) -> None:
    client = AsyncOpenAI()
    await client.models.retrieve(model_name)


@router.get("/health/ready")
async def readiness(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    config = request.app.state.config
    cache: ReadinessCache = request.app.state.readiness_cache

    db_ok = True
    db_error = None
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    llm_ok, llm_error = await cache.check(lambda: _probe_llm(config.model.name))

    status_code = 200 if db_ok and llm_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if db_ok and llm_ok else "degraded",
            "db": "ok" if db_ok else "error",
            "llm": "ok" if llm_ok else "error",
            "errors": {
                "db": db_error,
                "llm": llm_error,
            },
        },
    )
