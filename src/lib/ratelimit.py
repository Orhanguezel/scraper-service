import time
from fastapi import HTTPException, status
from redis.asyncio import Redis

from src.config import get_settings


async def enforce_rate_limit(redis: Redis, key_hash: str) -> None:
    settings = get_settings()
    bucket = int(time.time() // 60)
    redis_key = f"ratelimit:{key_hash}:{bucket}"
    count = await redis.incr(redis_key)
    if count == 1:
        await redis.expire(redis_key, 90)
    if count > settings.default_rate_limit_per_minute:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limit_exceeded")
