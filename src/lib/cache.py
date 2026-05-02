import hashlib
import json
from typing import Any
from redis.asyncio import Redis

from src.config import get_settings
from src.schemas.scrape import ScrapeRequest


def build_cache_key(request: ScrapeRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"return_html", "return_text"})
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "scrape:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get_cached(redis: Redis, key: str) -> dict[str, Any] | None:
    raw = await redis.get(key)
    if not raw:
        return None
    return json.loads(raw)


async def set_cached(redis: Redis, key: str, value: dict[str, Any]) -> None:
    await redis.set(key, json.dumps(value), ex=get_settings().cache_ttl_seconds)
