"""A fork-safe bridge from synchronous Celery tasks to async repositories."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import TypeVar

from celery.signals import worker_process_shutdown
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from services.api.app.config.settings import get_worker_settings

T = TypeVar("T")


class CeleryAsyncRuntime:
    def __init__(self) -> None:
        self._pid: int | None = None
        self._runner: asyncio.Runner | None = None
        self._engine: AsyncEngine | None = None
        self._factory: async_sessionmaker[AsyncSession] | None = None

    def _ensure_current_process(self) -> None:
        pid = os.getpid()
        if (
            self._pid == pid
            and self._runner is not None
            and self._engine is not None
            and self._factory is not None
        ):
            return
        self._pid = pid
        self._runner = asyncio.Runner()
        self._engine = create_async_engine(get_worker_settings().database_url, pool_pre_ping=True)
        self._factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    def run(
        self,
        operation: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]],
    ) -> T:
        self._ensure_current_process()
        assert self._runner is not None and self._factory is not None
        return self._runner.run(operation(self._factory))

    def close(self) -> None:
        if self._runner is None or self._engine is None:
            return
        self._runner.run(self._engine.dispose())
        self._runner.close()
        self._runner = None
        self._engine = None
        self._factory = None
        self._pid = None


runtime = CeleryAsyncRuntime()


@worker_process_shutdown.connect
def _close_worker_runtime(**_kwargs) -> None:
    runtime.close()
