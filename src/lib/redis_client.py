from __future__ import annotations

import fnmatch
import time
from functools import lru_cache
from typing import Any
from redis.asyncio import Redis

from src.config import get_settings


class MemoryRedis:
    """Tiny Redis-compatible adapter for local smoke tests without Docker/Redis."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._expires: dict[str, float] = {}

    def _expired(self, key: str) -> bool:
        expires_at = self._expires.get(key)
        if expires_at is None or expires_at > time.time():
            return False
        self._values.pop(key, None)
        self._hashes.pop(key, None)
        self._expires.pop(key, None)
        return True

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        if self._expired(key):
            return None
        return self._values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._values[key] = value
        if ex:
            self._expires[key] = time.time() + ex
        return True

    async def hgetall(self, key: str) -> dict[str, str]:
        if self._expired(key):
            return {}
        return dict(self._hashes.get(key, {}))

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        target = self._hashes.setdefault(key, {})
        before = len(target)
        target.update({k: str(v) for k, v in mapping.items()})
        return len(target) - before

    async def expire(self, key: str, seconds: int) -> bool:
        self._expires[key] = time.time() + seconds
        return True

    async def incr(self, key: str) -> int:
        if self._expired(key):
            self._values.pop(key, None)
        value = int(self._values.get(key, "0")) + 1
        self._values[key] = str(value)
        return value

    async def keys(self, pattern: str) -> list[str]:
        keys = set(self._values.keys()) | set(self._hashes.keys())
        return [key for key in keys if not self._expired(key) and fnmatch.fnmatch(key, pattern)]


@lru_cache(maxsize=1)
def get_redis_client() -> Redis | MemoryRedis:
    redis_url = get_settings().redis_url
    if redis_url == "memory://" or redis_url.startswith("memory://"):
        return MemoryRedis()
    return Redis.from_url(redis_url, decode_responses=True)


async def get_redis() -> Redis | MemoryRedis:
    return get_redis_client()
